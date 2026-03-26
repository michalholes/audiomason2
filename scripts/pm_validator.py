from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

PATCH_RE = re.compile(r"^issue_(?P<issue>\d+)_v(?P<version>[1-9]\d*)\.zip$")
SNAPSHOT_TARGET_RE = re.compile(r"^(?P<target>.+)-main_[^/]+\.zip$")
PATCH_PREFIX = "patches/per_file/"
PATCH_SUFFIX = ".patch"
TARGET_FILE_NAME = "target.txt"
LINE_EXTS = {".py", ".js"}
JS_EXTS = {".js", ".mjs", ".cjs"}
CATCHALL_BASENAMES = {"utils.py", "common.py", "helpers.py", "misc.py"}
CATCHALL_DIRS = {"utils", "common", "helpers", "misc"}
AREAS = {"src", "plugins", "badguys", "scripts", "tests", "docs"}
HUB_FANIN_DELTA = 5
HUB_FANOUT_DELTA = 5
HUB_EXPORTS_DELTA_MIN = 3
HUB_LOC_DELTA_MIN = 100

_RE_EXPORT_LINE = re.compile(r"^\s*export\s+", re.MULTILINE)
_RE_EXPORTS_DOT = re.compile(r"\bexports\.([A-Za-z0-9_$]+)")
_RE_IMPORT_FROM = re.compile(r"\bimport\b[^;\n]*\bfrom\s*[\"']([^\"']+)[\"']")
_RE_EXPORT_FROM = re.compile(r"\bexport\b[^;\n]*\bfrom\s*[\"']([^\"']+)[\"']")
_RE_REQUIRE = re.compile(r"\brequire\(\s*[\"']([^\"']+)[\"']\s*\)")


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    status: str
    detail: str


@dataclass(frozen=True)
class MonolithMetrics:
    loc: int
    internal_imports: int
    exports: int


class ValidationError(Exception):
    pass


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)


def _read_zip(path: Path) -> tuple[list[str], dict[str, bytes]]:
    with ZipFile(path, "r") as zf:
        names = zf.namelist()
        items = {name: zf.read(name) for name in names if not name.endswith("/")}
    return names, items


def _decode_ascii_text(raw: bytes) -> str | None:
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    return text[:-1] if text.endswith("\n") else text


def _decode_ascii_raw(raw: bytes) -> str | None:
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError:
        return None


def _zip_text(items: dict[str, bytes], name: str) -> str | None:
    raw = items.get(name)
    return None if raw is None else _decode_ascii_text(raw)


def _validate_target_bytes(raw: bytes) -> tuple[str | None, str | None]:
    text = _decode_ascii_raw(raw)
    if text is None:
        return None, "target_must_be_ascii"
    if "\r" in text:
        return None, "target_must_use_lf_newlines"
    value = text[:-1] if text.endswith("\n") else text
    if "\n" in value:
        return None, "target_must_have_exactly_one_line"
    if value == "":
        return None, "target_must_be_non_empty"
    return value, None


def _target_rule(items: dict[str, bytes]) -> tuple[RuleResult, str | None]:
    raw = items.get(TARGET_FILE_NAME)
    if raw is None:
        return RuleResult("TARGET_FILE", "FAIL", "missing_target_file"), None
    value, err = _validate_target_bytes(raw)
    if err is not None:
        return RuleResult("TARGET_FILE", "FAIL", err), None
    assert value is not None
    return RuleResult("TARGET_FILE", "PASS", value), value


def _is_ascii_text(text: str) -> bool:
    return text.isascii()


def _is_ascii_bytes(raw: bytes) -> bool:
    return _decode_ascii_raw(raw) is not None


def _validate_basename(path: Path, issue_id: str) -> RuleResult:
    match = PATCH_RE.fullmatch(path.name)
    if match is None:
        return RuleResult("PATCH_BASENAME", "FAIL", f"invalid_patch_basename:{path.name}")
    actual = match.group("issue")
    if actual != issue_id:
        detail = f"issue_mismatch:expected={issue_id}:actual={actual}:name={path.name}"
        return RuleResult("PATCH_BASENAME", "FAIL", detail)
    return RuleResult("PATCH_BASENAME", "PASS", path.name)


def _snapshot_target(path: Path) -> str | None:
    match = SNAPSHOT_TARGET_RE.fullmatch(path.name)
    return None if match is None else match.group("target")


def _initial_target_source_rule(path: Path) -> tuple[RuleResult, str | None]:
    target = _snapshot_target(path)
    if target is None:
        detail = f"invalid_workspace_snapshot_basename:{path.name}"
        return RuleResult("INITIAL_TARGET_SOURCE", "FAIL", detail), None
    return RuleResult("INITIAL_TARGET_SOURCE", "PASS", target), target


def _repair_overlay_target_rule(path: Path) -> tuple[RuleResult, str | None]:
    raw = _iter_zip_files(path).get(TARGET_FILE_NAME)
    if raw is None:
        return RuleResult("REPAIR_TARGET_SOURCE", "FAIL", "missing_target_file"), None
    value, err = _validate_target_bytes(raw)
    if err is not None:
        return RuleResult("REPAIR_TARGET_SOURCE", "FAIL", err), None
    assert value is not None
    return RuleResult("REPAIR_TARGET_SOURCE", "PASS", value), value


def _target_match_rule(rule_id: str, expected: str, actual: str) -> RuleResult:
    detail = f"expected={expected}:actual={actual}"
    return RuleResult(rule_id, "PASS" if actual == expected else "FAIL", detail)


def _repair_snapshot_consistency_rule(path: Path, overlay_target: str) -> RuleResult:
    snapshot_target = _snapshot_target(path)
    if snapshot_target is None:
        detail = f"snapshot_basename_not_matching_contract:{path.name}"
        return RuleResult("REPAIR_TARGET_SNAPSHOT_CONSISTENCY", "SKIP", detail)
    detail = f"overlay={overlay_target}:snapshot={snapshot_target}"
    status = "PASS" if overlay_target == snapshot_target else "FAIL"
    return RuleResult("REPAIR_TARGET_SNAPSHOT_CONSISTENCY", status, detail)


def _member_repo_path(member: str) -> str | None:
    if not (member.startswith(PATCH_PREFIX) and member.endswith(PATCH_SUFFIX)):
        return None
    raw = member[len(PATCH_PREFIX) : -len(PATCH_SUFFIX)]
    if not raw or "/" in raw or raw.endswith("__"):
        return None
    return raw.replace("__", "/")


def _validate_patch_headers(expected_path: str, text: str) -> str | None:
    saw = False
    for line in text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            expected_old = f"a/{expected_path}"
            expected_new = f"b/{expected_path}"
            if len(parts) != 4 or parts[2] != expected_old or parts[3] != expected_new:
                return "diff_git_path_mismatch"
            saw = True
        elif line.startswith(("rename from ", "rename to ")):
            return "rename_not_supported"
        elif line.startswith("--- "):
            saw = True
            if line[4:] not in ("/dev/null", f"a/{expected_path}"):
                return "old_path_mismatch"
        elif line.startswith("+++ "):
            saw = True
            if line[4:] not in ("/dev/null", f"b/{expected_path}"):
                return "new_path_mismatch"
    return None if saw else "missing_patch_headers"


def _check_line_lengths(text: str) -> str | None:
    for idx, line in enumerate(text.splitlines(), start=1):
        if line.startswith("+++"):
            continue
        if line.startswith("+") and len(line[1:]) > 100:
            return f"added_line_too_long:line={idx}:len={len(line[1:])}"
    return None


def _collect_patch_members(
    path: Path,
    issue_id: str,
    commit_message: str,
) -> tuple[list[RuleResult], list[tuple[str, bytes]], list[str], str | None]:
    status = "PASS" if path.suffix == ".zip" else "FAIL"
    results = [RuleResult("PATCH_EXTENSION", status, str(path))]
    if path.suffix != ".zip":
        return results, [], [], None
    names, items = _read_zip(path)
    zmsg = _zip_text(items, "COMMIT_MESSAGE.txt")
    zid = _zip_text(items, "ISSUE_NUMBER.txt")
    results.append(
        RuleResult(
            "COMMIT_MESSAGE_FILE",
            "PASS" if zmsg == commit_message else "FAIL",
            zmsg if zmsg is not None else "missing_or_non_ascii_commit_message",
        )
    )
    results.append(
        RuleResult(
            "ISSUE_NUMBER_FILE",
            "PASS" if zid == issue_id else "FAIL",
            zid if zid is not None else "missing_or_non_ascii_issue_number",
        )
    )
    if zmsg != commit_message or zid != issue_id:
        return results, [], [], None
    target_rule, patch_target = _target_rule(items)
    results.append(target_rule)
    if target_rule.status != "PASS":
        return results, [], [], None
    non_dirs = [name for name in names if not name.endswith("/")]
    members = [
        name for name in non_dirs if name.startswith(PATCH_PREFIX) and name.endswith(PATCH_SUFFIX)
    ]
    if not members:
        return results + [RuleResult("PER_FILE_LAYOUT", "FAIL", "entries=0")], [], [], None
    allowed = {"COMMIT_MESSAGE.txt", "ISSUE_NUMBER.txt", TARGET_FILE_NAME, *members}
    extras = sorted(name for name in non_dirs if name not in allowed)
    if extras:
        detail = f"extra_entries={extras}"
        return results + [RuleResult("PER_FILE_LAYOUT", "FAIL", detail)], [], [], None
    results.append(RuleResult("PER_FILE_LAYOUT", "PASS", f"entries={len(members)}"))
    patch_members: list[tuple[str, bytes]] = []
    decision_paths: list[str] = []
    seen: set[str] = set()
    for member in sorted(members):
        repo_path = _member_repo_path(member)
        if repo_path is None:
            detail = f"invalid_member:{member}"
            return results + [RuleResult("PATCH_MEMBER_PATHS", "FAIL", detail)], [], [], None
        if not _is_ascii_text(member):
            detail = f"non_ascii_member:{member}"
            return results + [RuleResult("PATCH_MEMBER_PATHS", "FAIL", detail)], [], [], None
        if not _is_ascii_text(repo_path):
            detail = f"non_ascii_repo_path:{repo_path}"
            return results + [RuleResult("PATCH_MEMBER_PATHS", "FAIL", detail)], [], [], None
        if repo_path in seen:
            detail = f"duplicate_repo_path:{repo_path}"
            return results + [RuleResult("PATCH_MEMBER_PATHS", "FAIL", detail)], [], [], None
        seen.add(repo_path)
        if not _is_ascii_bytes(items[member]):
            detail = f"{member}:non_ascii_patch_text"
            return results + [RuleResult("PATCH_ASCII", "FAIL", detail)], [], [], None
        text = items[member].decode("ascii")
        header_err = _validate_patch_headers(repo_path, text)
        if header_err is not None:
            detail = f"{member}:{header_err}"
            return results + [RuleResult("PATCH_MEMBER_PATHS", "FAIL", detail)], [], [], None
        if Path(repo_path).suffix in LINE_EXTS:
            line_err = _check_line_lengths(text)
            if line_err is not None:
                detail = f"{member}:{line_err}"
                return results + [RuleResult("LINE_LENGTH", "FAIL", detail)], [], [], None
        patch_members.append((member, items[member]))
        decision_paths.append(repo_path)
    results.append(RuleResult("PATCH_MEMBER_PATHS", "PASS", f"paths={len(decision_paths)}"))
    results.append(RuleResult("PATCH_ASCII", "PASS", "patch_members_ascii_only"))
    results.append(RuleResult("LINE_LENGTH", "PASS", "py_js_added_lines<=100"))
    return results, patch_members, decision_paths, patch_target


def _docs_gate(decision_paths: list[str]) -> RuleResult:
    if not any(path.startswith(("src/", "plugins/", "docs/")) for path in decision_paths):
        return RuleResult("DOCS_GATE", "PASS", "not_triggered")
    if any(path == "docs/changes.md" for path in decision_paths):
        return RuleResult("DOCS_GATE", "FAIL", "direct_changes_md_edit")
    has_fragment = any(path.startswith("docs/change_fragments/") for path in decision_paths)
    detail = "fragment_present" if has_fragment else "missing_change_fragment"
    return RuleResult("DOCS_GATE", "PASS" if has_fragment else "FAIL", detail)


def _iter_zip_files(path: Path) -> dict[str, bytes]:
    names, items = _read_zip(path)
    keep = {
        name: items[name]
        for name in names
        if not name.endswith("/") and not name.startswith(".am_patch/")
    }
    keep.pop("COMMIT_MESSAGE.txt", None)
    keep.pop("ISSUE_NUMBER.txt", None)
    return keep


def _authority_files(
    args: argparse.Namespace,
    decision_paths: list[str],
) -> tuple[dict[str, bytes], str]:
    if not args.repair_overlay:
        snapshot = _iter_zip_files(Path(args.workspace_snapshot))
        baseline = {path: snapshot[path] for path in decision_paths if path in snapshot}
        return baseline, "initial"
    overlay = _iter_zip_files(Path(args.repair_overlay))
    baseline = {path: overlay[path] for path in decision_paths if path in overlay}
    if not args.supplemental_file:
        missing = [path for path in decision_paths if path not in baseline]
        if missing:
            raise ValidationError(f"repair_requires_supplemental_file:{missing}")
        return baseline, "overlay-only"
    if not args.workspace_snapshot:
        raise ValidationError("supplemental_requires_workspace_snapshot")
    snapshot = _iter_zip_files(Path(args.workspace_snapshot))
    allowed = set(args.supplemental_file)
    undeclared = [path for path in decision_paths if path not in baseline and path not in allowed]
    if undeclared:
        raise ValidationError(f"repair_requires_supplemental_file:{undeclared}")
    missing = [path for path in allowed if path not in snapshot]
    if missing:
        raise ValidationError(f"supplemental_file_missing_in_snapshot:{sorted(missing)}")
    for path in decision_paths:
        if path in allowed and path in snapshot:
            baseline[path] = snapshot[path]
    return baseline, "overlay+supplemental"


def _write_tree(root: Path, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)


def _apply_patches(root: Path, patch_members: list[tuple[str, bytes]]) -> list[RuleResult]:
    out: list[RuleResult] = []
    for member, data in patch_members:
        patch_file = root / ".pm_validator" / Path(member).name
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_bytes(data)
        proc = _run(["git", "apply", "--check", str(patch_file)], cwd=root)
        detail = (
            "ok" if proc.returncode == 0 else (proc.stderr.strip() or proc.stdout.strip() or "fail")
        )
        status = "PASS" if proc.returncode == 0 else "FAIL"
        out.append(RuleResult(f"GIT_APPLY_CHECK:{member}", status, detail))
        if proc.returncode != 0:
            return out
        apply_proc = _run(["git", "apply", str(patch_file)], cwd=root)
        if apply_proc.returncode != 0:
            detail = apply_proc.stderr.strip() or apply_proc.stdout.strip() or member
            raise ValidationError(detail)
    return out


def _compile_python(root: Path, decision_paths: list[str]) -> RuleResult:
    targets = [
        str(root / path)
        for path in decision_paths
        if path.endswith(".py") and (root / path).exists()
    ]
    if not targets:
        return RuleResult("PY_COMPILE", "SKIP", "no_modified_python_files")
    proc = _run([sys.executable, "-m", "compileall", "-q", *targets], cwd=root)
    detail = f"files={len(targets)}"
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "compileall_failed"
    return RuleResult("PY_COMPILE", "PASS" if proc.returncode == 0 else "FAIL", detail)


def _check_js(root: Path, decision_paths: list[str]) -> RuleResult:
    targets = [
        str(root / path)
        for path in decision_paths
        if Path(path).suffix in JS_EXTS and (root / path).exists()
    ]
    if not targets:
        return RuleResult("JS_SYNTAX", "SKIP", "no_modified_javascript_files")
    node = shutil.which("node")
    if node is None:
        return RuleResult("JS_SYNTAX", "SKIP", "node_not_found")
    for target in targets:
        proc = _run([node, "--check", target], cwd=root)
        if proc.returncode != 0:
            detail = proc.stderr.strip() or proc.stdout.strip() or target
            return RuleResult("JS_SYNTAX", "FAIL", detail)
    return RuleResult("JS_SYNTAX", "PASS", f"files={len(targets)}")


def _count_loc(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip())


def _parse_tree(text: str) -> ast.AST | None:
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def _count_exports(tree: ast.AST) -> int:
    if not isinstance(tree, ast.Module):
        return 0
    total = 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = getattr(node, "name", "")
            if name and not name.startswith("_"):
                total += 1
    return total


def _norm_relpath(path: str) -> str:
    text = str(path).replace("\\", "/").strip()
    if text.startswith("./"):
        text = text[2:]
    return text.strip("/")


def _area(path: str) -> str:
    parts = PurePosixPath(path).parts
    first = parts[0] if parts else ""
    if first == "plugins" and len(parts) >= 2:
        return f"plugins.{parts[1]}"
    return first if first in AREAS else "other"


def _module_for_relpath(relpath: str) -> str | None:
    rp = _norm_relpath(relpath)
    if rp.startswith("src/audiomason/") and rp.endswith(".py"):
        sub = rp[len("src/") : -3].replace("/", ".")
        return sub[: -len(".__init__")] if sub.endswith(".__init__") else sub
    if rp.startswith("scripts/am_patch/") and rp.endswith(".py"):
        sub = rp[len("scripts/") : -3].replace("/", ".")
        return sub[: -len(".__init__")] if sub.endswith(".__init__") else sub
    if rp.startswith("plugins/") and rp.endswith(".py"):
        parts = rp.split("/")
        if len(parts) >= 2:
            name = parts[1]
            rest = "/".join(parts[2:])
            if rest == "__init__.py":
                return f"plugins.{name}"
            if rest.endswith(".py"):
                rest = rest[:-3]
            rest = rest.replace("/", ".")
            return f"plugins.{name}.{rest}" if rest else f"plugins.{name}"
    if rp.startswith("tests/") and rp.endswith(".py"):
        sub = rp[:-3].replace("/", ".")
        return sub[: -len(".__init__")] if sub.endswith(".__init__") else sub
    return None


def _module_to_rel_hint(mod: str) -> str | None:
    text = str(mod).strip().strip(".")
    if not text:
        return None
    parts = text.split(".")
    root = parts[0]
    if root == "audiomason":
        rest = "/".join(parts[1:])
        return f"src/audiomason/{rest}.py" if rest else "src/audiomason/__init__.py"
    if root == "am_patch":
        rest = "/".join(parts[1:])
        return f"scripts/am_patch/{rest}.py" if rest else "scripts/am_patch/__init__.py"
    if root == "plugins" and len(parts) >= 2:
        name = parts[1]
        rest = "/".join(parts[2:])
        return f"plugins/{name}/{rest}.py" if rest else f"plugins/{name}/__init__.py"
    if root == "tests":
        rest = "/".join(parts[1:])
        return f"tests/{rest}.py" if rest else "tests/__init__.py"
    return None


def _area_for_module(mod: str) -> str:
    hint = _module_to_rel_hint(mod)
    return "other" if hint is None else _area(hint)


def _iter_import_modules(tree: ast.AST, *, current_module: str | None) -> list[str]:
    modules: list[str] = []

    def add(mod: str) -> None:
        text = str(mod).strip().strip(".")
        if text and text not in modules:
            modules.append(text)

    def resolve_relative(level: int, mod: str | None) -> str | None:
        if not current_module or level <= 0:
            return None
        parts = current_module.split(".")
        if parts:
            parts = parts[:-1]
        up = max(0, min(level - 1, len(parts)))
        base = parts[: len(parts) - up]
        if mod:
            text = str(mod).strip(".")
            if not text:
                return ".".join(base) or None
            return ".".join([*base, text]) if base else text
        return ".".join(base) or None

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                resolved = resolve_relative(node.level, node.module)
                if resolved:
                    add(resolved)
                continue
            if node.module:
                add(node.module)

    return modules


def _count_js_exports(text: str) -> int:
    export_lines = len(_RE_EXPORT_LINE.findall(text))
    module_exports = text.count("module.exports")
    dotted = {match.group(1) for match in _RE_EXPORTS_DOT.finditer(text)}
    return export_lines + module_exports + len(dotted)


def _iter_js_specs(text: str) -> list[str]:
    specs: list[str] = []

    def add(spec: str) -> None:
        value = str(spec).strip()
        if value and value not in specs:
            specs.append(value)

    for rx in (_RE_IMPORT_FROM, _RE_EXPORT_FROM, _RE_REQUIRE):
        for match in rx.finditer(text):
            add(match.group(1))
    return specs


def _resolve_js_spec(relpath: str, spec: str, known_paths: set[str]) -> str | None:
    value = str(spec).strip()
    if not (value.startswith("./") or value.startswith("../")):
        return None
    for sep in ("?", "#"):
        if sep in value:
            value = value.split(sep, 1)[0]
    base = PurePosixPath(_norm_relpath(relpath)).parent
    candidate = _norm_relpath(str(base / value))
    options = [candidate]
    if not any(candidate.endswith(ext) for ext in JS_EXTS):
        options.append(candidate + ".js")
        options.append(_norm_relpath(candidate + "/index.js"))
    for option in options:
        if option in known_paths:
            return option
    return options[0] if options else None


def _py_metrics(relpath: str, text: str) -> MonolithMetrics:
    tree = _parse_tree(text)
    if tree is None:
        return MonolithMetrics(loc=_count_loc(text), internal_imports=0, exports=0)
    current_module = _module_for_relpath(relpath)
    internal_mods = {
        mod
        for mod in _iter_import_modules(tree, current_module=current_module)
        if _area_for_module(mod) != "other"
    }
    return MonolithMetrics(
        loc=_count_loc(text),
        internal_imports=len(internal_mods),
        exports=_count_exports(tree),
    )


def _js_metrics(relpath: str, text: str, known_paths: set[str]) -> MonolithMetrics:
    internal_targets = {
        target
        for spec in _iter_js_specs(text)
        if (target := _resolve_js_spec(relpath, spec, known_paths)) is not None
        and _area(target) != "other"
    }
    return MonolithMetrics(
        loc=_count_loc(text),
        internal_imports=len(internal_targets),
        exports=_count_js_exports(text),
    )


def _metrics_for_path(relpath: str, text: str, known_paths: set[str]) -> MonolithMetrics:
    suffix = Path(relpath).suffix
    if suffix == ".py":
        return _py_metrics(relpath, text)
    if suffix in JS_EXTS:
        return _js_metrics(relpath, text, known_paths)
    return MonolithMetrics(loc=_count_loc(text), internal_imports=0, exports=0)


def _resolve_fan_target(mod: str, module_to_rel: dict[str, str]) -> str | None:
    current = str(mod).strip().strip(".")
    if not current:
        return None
    while True:
        if current in module_to_rel:
            return module_to_rel[current]
        if "." not in current:
            return None
        current = current.rsplit(".", 1)[0]


def _fan_graph(texts: dict[str, str], relpaths: list[str]) -> tuple[dict[str, int], dict[str, int]]:
    module_to_rel = {
        module: relpath
        for relpath in relpaths
        if (module := _module_for_relpath(relpath)) is not None
    }
    known_paths = set(relpaths)
    edges: dict[str, set[str]] = {relpath: set() for relpath in relpaths}
    for relpath in relpaths:
        text = texts.get(relpath)
        if text is None:
            continue
        if relpath.endswith(".py"):
            tree = _parse_tree(text)
            if tree is None:
                continue
            current_module = _module_for_relpath(relpath)
            for mod in _iter_import_modules(tree, current_module=current_module):
                target = _resolve_fan_target(mod, module_to_rel)
                if target and target != relpath:
                    edges[relpath].add(target)
        elif Path(relpath).suffix in JS_EXTS:
            for spec in _iter_js_specs(text):
                target = _resolve_js_spec(relpath, spec, known_paths)
                if target in edges and target != relpath:
                    edges[relpath].add(target)
    fanout = {relpath: len(edges[relpath]) for relpath in relpaths}
    fanin = {relpath: 0 for relpath in relpaths}
    for targets in edges.values():
        for target in targets:
            fanin[target] = fanin.get(target, 0) + 1
    return fanin, fanout


def _hub_failure(
    *,
    path: str,
    fanin_delta: int,
    fanout_delta: int,
    loc_delta: int,
    exports_delta: int,
) -> RuleResult | None:
    if fanin_delta >= HUB_FANIN_DELTA and exports_delta >= HUB_EXPORTS_DELTA_MIN:
        detail = f"hub_signal_fanin:{path}:fanin_delta={fanin_delta}:exports_delta={exports_delta}"
        return RuleResult("MONOLITH", "FAIL", detail)
    if fanout_delta >= HUB_FANOUT_DELTA and loc_delta >= HUB_LOC_DELTA_MIN:
        detail = f"hub_signal_fanout:{path}:fanout_delta={fanout_delta}:loc_delta={loc_delta}"
        return RuleResult("MONOLITH", "FAIL", detail)
    return None


def _monolith(root: Path, baseline: dict[str, bytes], decision_paths: list[str]) -> RuleResult:
    targets = [
        path for path in decision_paths if Path(path).suffix in LINE_EXTS and (root / path).exists()
    ]
    if not targets:
        return RuleResult("MONOLITH", "SKIP", "no_modified_python_or_javascript_files")
    areas = {_area(path) for path in targets}
    if len(areas) >= 3:
        return RuleResult("MONOLITH", "FAIL", f"cross_area_threshold:areas={sorted(areas)}")

    new_texts = {path: (root / path).read_text(encoding="utf-8") for path in targets}
    old_texts = {path: baseline[path].decode("utf-8") for path in targets if path in baseline}
    known_paths = set(targets)
    new_fanin, new_fanout = _fan_graph(new_texts, targets)
    old_fanin, old_fanout = _fan_graph(old_texts, targets)

    for path in targets:
        posix = PurePosixPath(path)
        has_bad_dir = any(part in CATCHALL_DIRS for part in posix.parts[:-1])
        if posix.name in CATCHALL_BASENAMES or has_bad_dir:
            return RuleResult("MONOLITH", "FAIL", f"catchall_forbidden:{path}")

        new_metrics = _metrics_for_path(path, new_texts[path], known_paths)
        fanin_delta = new_fanin.get(path, 0) - old_fanin.get(path, 0)
        fanout_delta = new_fanout.get(path, 0) - old_fanout.get(path, 0)
        old_text = old_texts.get(path)
        if old_text is None:
            if (
                new_metrics.loc > 400
                or new_metrics.exports > 25
                or new_metrics.internal_imports > 15
            ):
                return RuleResult("MONOLITH", "FAIL", f"new_file_limits:{path}")
            hub_failure = _hub_failure(
                path=path,
                fanin_delta=fanin_delta,
                fanout_delta=fanout_delta,
                loc_delta=new_metrics.loc,
                exports_delta=new_metrics.exports,
            )
            if hub_failure is not None:
                return hub_failure
            continue

        old_metrics = _metrics_for_path(path, old_text, known_paths)
        loc_delta = new_metrics.loc - old_metrics.loc
        imports_delta = new_metrics.internal_imports - old_metrics.internal_imports
        exports_delta = new_metrics.exports - old_metrics.exports
        grew = any(value > 0 for value in (loc_delta, imports_delta, exports_delta))
        tier = None
        if new_metrics.loc >= 1300:
            tier = "huge"
        elif new_metrics.loc >= 900:
            tier = "large"
        if tier == "huge" and grew:
            return RuleResult("MONOLITH", "FAIL", f"huge_file_growth:{path}")
        if tier == "large" and (loc_delta > 20 or exports_delta > 2 or imports_delta > 1):
            return RuleResult("MONOLITH", "FAIL", f"large_file_growth:{path}")
        hub_failure = _hub_failure(
            path=path,
            fanin_delta=fanin_delta,
            fanout_delta=fanout_delta,
            loc_delta=loc_delta,
            exports_delta=exports_delta,
        )
        if hub_failure is not None:
            return hub_failure
    return RuleResult("MONOLITH", "PASS", "gate_passed")



INSTRUCTIONS_REQUIRED = {"HANDOFF.md", "constraint_pack.json", "hash_pack.txt"}
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
SUPPORTED_BINDING_TYPES = {"resolver_contract", "constraint_pack"}
BINDING_REQUIRED_FIELDS = (
    "id",
    "binding_type",
    "match",
    "symbol_role",
    "authoritative_semantics",
    "peer_renderers",
    "shared_contract_refs",
    "downstream_consumers",
    "exception_state_refs",
    "required_wiring",
    "forbidden",
    "required_validation",
    "verification_mode",
    "verification_method",
    "semantic_group",
    "conflict_policy",
)
AUTHORITY_ONLY_PATHS = {
    "docs/instructions_project_chats.txt",
    "docs/am_patch_instructions.md",
    "docs/pm_spec.md",
    "docs/specification.jsonl",
    "docs/validate_master_spec_v2.py",
    "scripts/authority_resolver.py",
}


def _decode_utf8_text(raw: bytes) -> str | None:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _normalize_single_ascii_line(raw: bytes) -> tuple[str | None, str | None]:
    text = _decode_ascii_raw(raw)
    if text is None:
        return None, "non_ascii"
    if "\r" in text:
        return None, "must_use_lf"
    value = text[:-1] if text.endswith("\n") else text
    if "\n" in value:
        return None, "must_have_exactly_one_line"
    if value == "":
        return None, "must_be_non_empty"
    return value, None


def _read_instructions_zip(path: Path) -> tuple[list[RuleResult], dict | None, bytes | None, str | None]:
    results: list[RuleResult] = []
    status = "PASS" if path.suffix == ".zip" else "FAIL"
    results.append(RuleResult("INSTRUCTIONS_EXTENSION", status, str(path)))
    if path.suffix != ".zip":
        return results, None, None, None
    names, items = _read_zip(path)
    non_dirs = [name for name in names if not name.endswith("/")]
    root_entries = sorted(non_dirs)
    expected = sorted(INSTRUCTIONS_REQUIRED)
    results.append(
        RuleResult(
            "INSTRUCTIONS_LAYOUT",
            "PASS" if root_entries == expected else "FAIL",
            f"entries={','.join(root_entries)}",
        )
    )
    handoff_raw = items.get("HANDOFF.md")
    pack_raw = items.get("constraint_pack.json")
    hash_raw = items.get("hash_pack.txt")
    handoff_text = None if handoff_raw is None else _decode_utf8_text(handoff_raw)
    if handoff_text is None:
        results.append(RuleResult("INSTRUCTIONS_HANDOFF", "FAIL", "missing_or_non_utf8_handoff"))
    else:
        status = "PASS" if "SPEC CONTEXT" in handoff_text else "FAIL"
        detail = "spec_context_present" if status == "PASS" else "missing_spec_context"
        results.append(RuleResult("INSTRUCTIONS_HANDOFF", status, detail))
    pack_obj = None
    if pack_raw is None:
        results.append(RuleResult("INSTRUCTIONS_PACK", "FAIL", "missing_constraint_pack"))
    else:
        pack_text = _decode_utf8_text(pack_raw)
        if pack_text is None:
            results.append(RuleResult("INSTRUCTIONS_PACK", "FAIL", "constraint_pack_non_utf8"))
        else:
            try:
                pack_obj = json.loads(pack_text)
                results.append(RuleResult("INSTRUCTIONS_PACK", "PASS", "json_ok"))
            except json.JSONDecodeError as exc:
                results.append(RuleResult("INSTRUCTIONS_PACK", "FAIL", f"json_error:{exc.msg}"))
    hash_value = None
    if hash_raw is None:
        results.append(RuleResult("INSTRUCTIONS_HASH", "FAIL", "missing_hash_pack"))
    else:
        hash_value, err = _normalize_single_ascii_line(hash_raw)
        if err is not None or hash_value is None or HEX64_RE.fullmatch(hash_value) is None:
            detail = err or "invalid_hash_format"
            results.append(RuleResult("INSTRUCTIONS_HASH", "FAIL", detail))
        else:
            results.append(RuleResult("INSTRUCTIONS_HASH", "PASS", hash_value))
    if pack_raw is not None and hash_value is not None and HEX64_RE.fullmatch(hash_value or "") is not None:
        actual_hash = hashlib.sha256(pack_raw).hexdigest()
        results.append(
            RuleResult(
                "PACK_HASH_INTEGRITY",
                "PASS" if actual_hash == hash_value else "FAIL",
                f"expected={hash_value}:actual={actual_hash}",
            )
        )
    return results, pack_obj, pack_raw, hash_value


def _load_jsonl_bytes(raw: bytes) -> list[dict]:
    text = raw.decode("utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _collect_binding_meta_and_bindings(objects: list[dict]) -> tuple[dict, list[dict]]:
    binding_meta = None
    bindings: list[dict] = []
    seen_ids: set[str] = set()
    for obj in objects:
        obj_type = obj.get("type")
        if obj_type == "binding_meta":
            if binding_meta is not None:
                raise ValidationError("binding_meta_duplicate")
            binding_meta = obj
            continue
        if obj_type != "obligation_binding":
            continue
        binding_id = str(obj.get("id", "<missing-id>"))
        if binding_id in seen_ids:
            raise ValidationError(f"binding_duplicate:{binding_id}")
        seen_ids.add(binding_id)
        missing = [field for field in BINDING_REQUIRED_FIELDS if field not in obj]
        if missing:
            raise ValidationError(f"binding_missing_fields:{binding_id}:{','.join(missing)}")
        if obj["binding_type"] not in SUPPORTED_BINDING_TYPES:
            raise ValidationError(f"binding_type_unsupported:{binding_id}:{obj['binding_type']}")
        for field in ("verification_mode", "verification_method", "semantic_group", "conflict_policy"):
            if not str(obj.get(field, "")).strip():
                raise ValidationError(f"binding_empty_field:{binding_id}:{field}")
        bindings.append(obj)
    if binding_meta is None:
        raise ValidationError("binding_meta_missing")
    return binding_meta, bindings


def _binding_is_active(binding: dict, mode: str, target_scope: str) -> bool:
    match = binding.get("match", {})
    if binding.get("binding_type") == "constraint_pack":
        return True
    return match.get("phase") == mode and match.get("target") == target_scope


def _ensure_binding_consistency(active_bindings: list[dict]) -> None:
    if not active_bindings:
        raise ValidationError("binding_active_missing")
    symbol_matches: dict[tuple[str, str], list[str]] = {}
    semantics: dict[str, list[str]] = {}
    role_semantics: dict[str, set[str]] = {}
    for binding in active_bindings:
        binding_id = binding["id"]
        match_key = json.dumps(binding.get("match", {}), sort_keys=True)
        symbol_key = (match_key, binding["symbol_role"])
        symbol_matches.setdefault(symbol_key, []).append(binding_id)
        semantics.setdefault(binding["authoritative_semantics"], []).append(binding_id)
        role_semantics.setdefault(binding["symbol_role"], set()).add(binding["authoritative_semantics"])
    for ids in symbol_matches.values():
        if len(ids) > 1:
            raise ValidationError(f"binding_ambiguous_symbol:{','.join(sorted(ids))}")
    for ids in semantics.values():
        if len(ids) > 1:
            raise ValidationError(f"binding_duplicate_semantics:{','.join(sorted(ids))}")
    for role, values in role_semantics.items():
        if len(values) > 1:
            raise ValidationError(f"binding_conflicting_obligations:{role}")


def _build_pack_from_spec_bytes(spec_raw: bytes, mode: str, target_scope: str) -> tuple[bytes, str, list[dict]]:
    objects = _load_jsonl_bytes(spec_raw)
    if not objects or objects[0].get("type") != "meta":
        raise ValidationError("spec_meta_missing")
    binding_meta, bindings = _collect_binding_meta_and_bindings(objects)
    active_bindings = [binding for binding in bindings if _binding_is_active(binding, mode, target_scope)]
    _ensure_binding_consistency(active_bindings)
    spec_fingerprint = hashlib.sha256(spec_raw).hexdigest()
    active_rule_ids = [binding["id"] for binding in active_bindings]
    pack = {
        "target_symbol": None,
        "target_scope": target_scope,
        "mode": mode,
        "spec_fingerprint": spec_fingerprint,
        "binding_meta_id": binding_meta["id"],
        "active_bindings": active_bindings,
        "active_rule_ids": active_rule_ids,
        "full_rule_text": {binding["id"]: binding["authoritative_semantics"] for binding in active_bindings},
        "match_basis": {binding["id"]: binding.get("match", {}) for binding in active_bindings},
        "authoritative_sources": ["docs/specification.jsonl"],
        "shared_contracts": sorted({ref for binding in active_bindings for ref in binding.get("shared_contract_refs", [])}),
        "downstream_consumers": sorted({consumer for binding in active_bindings for consumer in binding.get("downstream_consumers", [])}),
        "exception_state_refs": sorted({ref for binding in active_bindings for ref in binding.get("exception_state_refs", [])}),
        "required_wiring": sorted({item for binding in active_bindings for item in binding.get("required_wiring", [])}),
        "forbidden_strategies": sorted({item for binding in active_bindings for item in binding.get("forbidden", [])}),
        "required_validation": sorted({item for binding in active_bindings for item in binding.get("required_validation", [])}),
        "verification_mode_per_rule": {binding["id"]: binding["verification_mode"] for binding in active_bindings},
        "verification_method_per_rule": {binding["id"]: binding["verification_method"] for binding in active_bindings},
        "oracle_refs": {binding["id"]: binding.get("oracle_ref") for binding in active_bindings},
        "aggregate_scope_metadata": {"binding_count": len(active_bindings), "mode": mode, "target_scope": target_scope},
    }
    pack_json = json.dumps(pack, indent=2, sort_keys=True, ensure_ascii=True)
    pack_bytes = (pack_json + "\n").encode("utf-8")
    return pack_bytes, hashlib.sha256(pack_bytes).hexdigest(), active_bindings


def _authority_spec_bytes(args: argparse.Namespace) -> tuple[bytes | None, str | None]:
    spec_path = "docs/specification.jsonl"
    if not args.repair_overlay:
        snapshot = _iter_zip_files(Path(args.workspace_snapshot))
        return snapshot.get(spec_path), None if spec_path in snapshot else "missing_spec_in_workspace_snapshot"
    overlay = _iter_zip_files(Path(args.repair_overlay))
    if spec_path in overlay:
        return overlay[spec_path], None
    if args.workspace_snapshot and spec_path in set(args.supplemental_file):
        snapshot = _iter_zip_files(Path(args.workspace_snapshot))
        if spec_path in snapshot:
            return snapshot[spec_path], None
        return None, "supplemental_spec_missing_in_snapshot"
    return None, "missing_spec_for_repair_recompute"


def _pack_union_rule(rule_id: str, pack: dict, key: str, active_bindings: list[dict], field: str) -> RuleResult:
    expected = sorted({item for binding in active_bindings for item in binding.get(field, [])})
    actual = sorted(pack.get(key, []))
    return RuleResult(rule_id, "PASS" if actual == expected else "FAIL", f"expected={expected}:actual={actual}")


def _scope_mapping_rule(decision_paths: list[str], pack: dict) -> RuleResult:
    target_scope = str(pack.get("target_scope", ""))
    if not decision_paths:
        return RuleResult("PACK_SCOPE_MAPPING", "FAIL", "no_patch_paths")
    if target_scope == "authority_scope":
        bad = [path for path in decision_paths if not (path.startswith("docs/") or path.startswith("scripts/"))]
        status = "PASS" if not bad else "FAIL"
        detail = "authority_paths_ok" if status == "PASS" else f"out_of_scope={bad}"
        return RuleResult("PACK_SCOPE_MAPPING", status, detail)
    if target_scope == "implementation_scope":
        bad = [path for path in decision_paths if path in AUTHORITY_ONLY_PATHS]
        status = "PASS" if not bad else "FAIL"
        detail = "implementation_paths_ok" if status == "PASS" else f"authority_paths={bad}"
        return RuleResult("PACK_SCOPE_MAPPING", status, detail)
    return RuleResult("PACK_SCOPE_MAPPING", "FAIL", f"unsupported_target_scope:{target_scope}")


def _forbidden_bypass_rule(patch_member_names: list[str], pack: dict, active_bindings: list[dict]) -> RuleResult:
    expected = sorted({item for binding in active_bindings for item in binding.get("forbidden", [])})
    actual = sorted(pack.get("forbidden_strategies", []))
    if actual != expected:
        return RuleResult("PACK_FORBIDDEN_BYPASS", "FAIL", f"expected={expected}:actual={actual}")
    forbidden_names = {"HANDOFF.md", "constraint_pack.json", "hash_pack.txt"}
    leaked = [name for name in patch_member_names if any(item in name for item in forbidden_names)]
    if leaked:
        return RuleResult("PACK_FORBIDDEN_BYPASS", "FAIL", f"patch_contains_instruction_artifacts:{leaked}")
    return RuleResult("PACK_FORBIDDEN_BYPASS", "PASS", "forbidden_bypass_checks_ok")


def _recompute_pack_rule(args: argparse.Namespace, pack: dict, pack_raw: bytes | None) -> tuple[RuleResult, list[dict] | None]:
    spec_raw, err = _authority_spec_bytes(args)
    if err is not None or spec_raw is None:
        return RuleResult("PACK_RECOMPUTE", "UNVERIFIED_ENVIRONMENT", err or "missing_authority_spec"), None
    mode = str(pack.get("mode", ""))
    target_scope = str(pack.get("target_scope", ""))
    if not mode or not target_scope:
        return RuleResult("PACK_RECOMPUTE", "FAIL", "missing_mode_or_target_scope"), None
    try:
        rebuilt_raw, _rebuilt_hash, active_bindings = _build_pack_from_spec_bytes(spec_raw, mode, target_scope)
    except ValidationError as exc:
        return RuleResult("PACK_RECOMPUTE", "FAIL", str(exc)), None
    if pack_raw is None:
        return RuleResult("PACK_RECOMPUTE", "FAIL", "missing_pack_bytes"), active_bindings
    status = "PASS" if rebuilt_raw == pack_raw else "FAIL"
    detail = "recompute_match" if status == "PASS" else "recompute_mismatch"
    return RuleResult("PACK_RECOMPUTE", status, detail), active_bindings


def _pack_rule_verdicts(pack: dict, active_bindings: list[dict] | None, support_rules: dict[str, RuleResult]) -> list[RuleResult]:
    verdicts: list[RuleResult] = []
    bindings = active_bindings if active_bindings is not None else pack.get("active_bindings", [])
    for binding in bindings:
        binding_id = str(binding.get("id", "<missing-id>"))
        mode = str(binding.get("verification_mode", "")).strip()
        if not mode:
            verdicts.append(RuleResult(f"PACK_RULE:{binding_id}", "FAIL", "missing_verification_mode"))
            continue
        if mode != "machine":
            verdicts.append(RuleResult(f"PACK_RULE:{binding_id}", "MANUAL_REVIEW_REQUIRED", f"mode={mode}"))
            continue
        failing = [rule for rule in support_rules.values() if rule.status != "PASS"]
        if failing:
            status = failing[0].status if failing[0].status in {"UNVERIFIED_ENVIRONMENT", "MANUAL_REVIEW_REQUIRED"} else "FAIL"
            verdicts.append(RuleResult(f"PACK_RULE:{binding_id}", status, failing[0].rule_id))
        else:
            detail = f"mode={binding.get('verification_mode')} method={binding.get('verification_method')}"
            verdicts.append(RuleResult(f"PACK_RULE:{binding_id}", "PASS", detail))
    return verdicts


def _verdict_coverage_rule(pack: dict, verdicts: list[RuleResult]) -> RuleResult:
    expected = sorted(str(binding.get("id", "<missing-id>")) for binding in pack.get("active_bindings", []))
    actual = sorted(rule.rule_id.split(":", 1)[1] for rule in verdicts if rule.rule_id.startswith("PACK_RULE:"))
    status = "PASS" if actual == expected else "FAIL"
    return RuleResult("PACK_VERDICT_COVERAGE", status, f"expected={expected}:actual={actual}")


def _pack_rules(args: argparse.Namespace, instructions_path: Path, decision_paths: list[str], patch_member_names: list[str]) -> tuple[list[RuleResult], dict | None]:
    results, pack, pack_raw, _hash_value = _read_instructions_zip(instructions_path)
    if pack is None:
        return results, None
    recompute_rule, active_bindings = _recompute_pack_rule(args, pack, pack_raw)
    results.append(recompute_rule)
    if active_bindings is None:
        active_bindings = pack.get("active_bindings", [])
    results.append(_pack_union_rule("PACK_REQUIRED_WIRING", pack, "required_wiring", active_bindings, "required_wiring"))
    results.append(_forbidden_bypass_rule(patch_member_names, pack, active_bindings))
    results.append(_pack_union_rule("PACK_DOWNSTREAM_COVERAGE", pack, "downstream_consumers", active_bindings, "downstream_consumers"))
    results.append(_pack_union_rule("PACK_REQUIRED_VALIDATION", pack, "required_validation", active_bindings, "required_validation"))
    results.append(_scope_mapping_rule(decision_paths, pack))
    support_rules = {rule.rule_id: rule for rule in results if rule.rule_id in {
        "PACK_HASH_INTEGRITY",
        "PACK_RECOMPUTE",
        "PACK_REQUIRED_WIRING",
        "PACK_FORBIDDEN_BYPASS",
        "PACK_DOWNSTREAM_COVERAGE",
        "PACK_REQUIRED_VALIDATION",
        "PACK_SCOPE_MAPPING",
    }}
    verdicts = _pack_rule_verdicts(pack, active_bindings, support_rules)
    results.extend(verdicts)
    results.append(_verdict_coverage_rule(pack, verdicts))
    return results, pack

def _format(results: list[RuleResult]) -> str:
    hard_fail_statuses = {"FAIL", "UNVERIFIED_ENVIRONMENT", "MANUAL_REVIEW_REQUIRED"}
    overall = "FAIL" if any(item.status in hard_fail_statuses for item in results) else "PASS"
    lines = [f"RESULT: {overall}"]
    lines.extend(f"RULE {item.rule_id}: {item.status} - {item.detail}" for item in results)
    return "\n".join(lines) + "\n"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Single-file PM validator for patch artifacts.")
    parser.add_argument("issue_id")
    parser.add_argument("commit_message")
    parser.add_argument("patch")
    parser.add_argument("instructions_zip")
    parser.add_argument(
        "--workspace-snapshot",
        help="Workspace snapshot zip for initial mode or supplemental files.",
    )
    parser.add_argument(
        "--repair-overlay",
        help="patched_issue*.zip overlay for repair mode.",
    )
    parser.add_argument(
        "--supplemental-file",
        action="append",
        default=[],
        help="Repeat per repo-relative file path allowed during repair escalation.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    try:
        if not Path(args.patch).is_file():
            raise ValidationError("patch_not_found")
        if not Path(args.instructions_zip).is_file():
            raise ValidationError("instructions_zip_not_found")
        if args.repair_overlay:
            if not Path(args.repair_overlay).is_file():
                raise ValidationError("repair_overlay_not_found")
        elif not args.workspace_snapshot:
            raise ValidationError("workspace_snapshot_required_for_initial_mode")
        if args.workspace_snapshot and not Path(args.workspace_snapshot).is_file():
            raise ValidationError("workspace_snapshot_not_found")
        if args.supplemental_file and not args.repair_overlay:
            raise ValidationError("supplemental_file_requires_repair_mode")
        patch_path = Path(args.patch).resolve()
        instructions_path = Path(args.instructions_zip).resolve()
        results = [_validate_basename(patch_path, args.issue_id)]
        more, patch_members, decision_paths, patch_target = _collect_patch_members(
            patch_path,
            args.issue_id,
            args.commit_message,
        )
        results.extend(more)
        if any(item.status == "FAIL" for item in results):
            sys.stdout.write(_format(results))
            return 1
        if patch_target is None:
            raise ValidationError("patch_target_missing_after_validation")
        if args.repair_overlay:
            repair_rule, overlay_target = _repair_overlay_target_rule(Path(args.repair_overlay))
            results.append(repair_rule)
            if overlay_target is not None:
                results.append(_target_match_rule("REPAIR_TARGET_MATCH", overlay_target, patch_target))
                if args.workspace_snapshot:
                    results.append(_repair_snapshot_consistency_rule(Path(args.workspace_snapshot), overlay_target))
        else:
            initial_rule, initial_target = _initial_target_source_rule(Path(args.workspace_snapshot))
            results.append(initial_rule)
            if initial_target is not None:
                results.append(_target_match_rule("INITIAL_TARGET_MATCH", initial_target, patch_target))
        if any(item.status == "FAIL" for item in results):
            sys.stdout.write(_format(results))
            return 1
        results.append(_docs_gate(decision_paths))
        patch_member_names = [member for member, _data in patch_members]
        pack_results, _pack = _pack_rules(args, instructions_path, decision_paths, patch_member_names)
        results.extend(pack_results)
        if any(item.status in {"FAIL", "UNVERIFIED_ENVIRONMENT", "MANUAL_REVIEW_REQUIRED"} for item in results):
            sys.stdout.write(_format(results))
            return 1
        baseline, _mode = _authority_files(args, decision_paths)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_tree(root, baseline)
            results.extend(_apply_patches(root, patch_members))
            if any(item.status == "FAIL" for item in results):
                sys.stdout.write(_format(results))
                return 1
            results.extend([
                _compile_python(root, decision_paths),
                _check_js(root, decision_paths),
                _monolith(root, baseline, decision_paths),
            ])
        sys.stdout.write(_format(results))
        return 0 if all(item.status not in {"FAIL", "UNVERIFIED_ENVIRONMENT", "MANUAL_REVIEW_REQUIRED"} for item in results) else 1
    except ValidationError as exc:
        sys.stdout.write(_format([RuleResult("VALIDATION_ERROR", "FAIL", str(exc))]))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
