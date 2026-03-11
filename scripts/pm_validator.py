from __future__ import annotations

import argparse
import ast
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

PATCH_RE = re.compile(r"^issue_(?P<issue>\d+)_v(?P<version>[1-9]\d*)\.zip$")
PATCH_PREFIX = "patches/per_file/"
PATCH_SUFFIX = ".patch"
LINE_EXTS = {".py", ".js"}
JS_EXTS = {".js", ".mjs", ".cjs"}
CATCHALL_BASENAMES = {"utils.py", "common.py", "helpers.py", "misc.py"}
CATCHALL_DIRS = {"utils", "common", "helpers", "misc"}
AREAS = {"src", "plugins", "badguys", "scripts", "tests", "docs"}


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    status: str
    detail: str


class ValidationError(Exception):
    pass


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)


def _read_zip(path: Path) -> tuple[list[str], dict[str, bytes]]:
    with ZipFile(path, "r") as zf:
        names = zf.namelist()
        items = {name: zf.read(name) for name in names if not name.endswith("/")}
    return names, items


def _zip_text(items: dict[str, bytes], name: str) -> str | None:
    raw = items.get(name)
    return None if raw is None else raw.decode("utf-8").rstrip("\n")


def _validate_basename(path: Path, issue_id: str) -> RuleResult:
    match = PATCH_RE.fullmatch(path.name)
    if match is None:
        return RuleResult("PATCH_BASENAME", "FAIL", f"invalid_patch_basename:{path.name}")
    actual = match.group("issue")
    if actual != issue_id:
        detail = f"issue_mismatch:expected={issue_id}:actual={actual}:name={path.name}"
        return RuleResult("PATCH_BASENAME", "FAIL", detail)
    return RuleResult("PATCH_BASENAME", "PASS", path.name)


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
) -> tuple[list[RuleResult], list[tuple[str, bytes]], list[str]]:
    status = "PASS" if path.suffix == ".zip" else "FAIL"
    results = [RuleResult("PATCH_EXTENSION", status, str(path))]
    if path.suffix != ".zip":
        return results, [], []
    names, items = _read_zip(path)
    zmsg = _zip_text(items, "COMMIT_MESSAGE.txt")
    zid = _zip_text(items, "ISSUE_NUMBER.txt")
    results.append(
        RuleResult(
            "COMMIT_MESSAGE_FILE",
            "PASS" if zmsg == commit_message else "FAIL",
            zmsg or "missing_commit_message",
        )
    )
    results.append(
        RuleResult(
            "ISSUE_NUMBER_FILE",
            "PASS" if zid == issue_id else "FAIL",
            zid or "missing_issue_number",
        )
    )
    if zmsg != commit_message or zid != issue_id:
        return results, [], []
    non_dirs = [name for name in names if not name.endswith("/")]
    members = [
        name for name in non_dirs if name.startswith(PATCH_PREFIX) and name.endswith(PATCH_SUFFIX)
    ]
    if not members:
        return results + [RuleResult("PER_FILE_LAYOUT", "FAIL", "entries=0")], [], []
    allowed = {"COMMIT_MESSAGE.txt", "ISSUE_NUMBER.txt", *members}
    extras = sorted(name for name in non_dirs if name not in allowed)
    if extras:
        detail = f"extra_entries={extras}"
        return results + [RuleResult("PER_FILE_LAYOUT", "FAIL", detail)], [], []
    results.append(RuleResult("PER_FILE_LAYOUT", "PASS", f"entries={len(members)}"))
    patch_members: list[tuple[str, bytes]] = []
    decision_paths: list[str] = []
    seen: set[str] = set()
    for member in sorted(members):
        repo_path = _member_repo_path(member)
        if repo_path is None:
            detail = f"invalid_member:{member}"
            return results + [RuleResult("PATCH_MEMBER_PATHS", "FAIL", detail)], [], []
        if repo_path in seen:
            detail = f"duplicate_repo_path:{repo_path}"
            return results + [RuleResult("PATCH_MEMBER_PATHS", "FAIL", detail)], [], []
        seen.add(repo_path)
        text = items[member].decode("utf-8")
        header_err = _validate_patch_headers(repo_path, text)
        if header_err is not None:
            detail = f"{member}:{header_err}"
            return results + [RuleResult("PATCH_MEMBER_PATHS", "FAIL", detail)], [], []
        if Path(repo_path).suffix in LINE_EXTS:
            line_err = _check_line_lengths(text)
            if line_err is not None:
                detail = f"{member}:{line_err}"
                return results + [RuleResult("LINE_LENGTH", "FAIL", detail)], [], []
        patch_members.append((member, items[member]))
        decision_paths.append(repo_path)
    results.append(RuleResult("PATCH_MEMBER_PATHS", "PASS", f"paths={len(decision_paths)}"))
    results.append(RuleResult("LINE_LENGTH", "PASS", "py_js_added_lines<=100"))
    return results, patch_members, decision_paths


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


def _py_counts(text: str) -> tuple[int, int]:
    tree = ast.parse(text)
    imports = sum(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(tree))
    exports = sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and not node.name.startswith("_")
        for node in tree.body
    )
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            is_all = isinstance(target, ast.Name) and target.id == "__all__"
            value = node.value
            if is_all and isinstance(value, (ast.List, ast.Tuple)):
                exports += sum(
                    isinstance(item, ast.Constant) and isinstance(item.value, str)
                    for item in value.elts
                )
    return imports, exports


def _js_counts(text: str) -> tuple[int, int]:
    imports = sum(1 for line in text.splitlines() if line.lstrip().startswith("import "))
    exports = sum(1 for line in text.splitlines() if line.lstrip().startswith("export "))
    return imports, exports + text.count("module.exports") + text.count("exports.")


def _counts(path: str, text: str) -> tuple[int, int, int]:
    loc = len(text.splitlines())
    suffix = Path(path).suffix
    if suffix == ".py":
        imports, exports = _py_counts(text)
    elif suffix in JS_EXTS:
        imports, exports = _js_counts(text)
    else:
        imports = exports = 0
    return loc, imports, exports


def _area(path: str) -> str:
    parts = PurePosixPath(path).parts
    first = parts[0] if parts else ""
    return first if first in AREAS else "other"


def _monolith(root: Path, baseline: dict[str, bytes], decision_paths: list[str]) -> RuleResult:
    targets = [
        path for path in decision_paths if Path(path).suffix in LINE_EXTS and (root / path).exists()
    ]
    if not targets:
        return RuleResult("MONOLITH", "SKIP", "no_modified_python_or_javascript_files")
    areas = {_area(path) for path in targets}
    if len(areas) >= 3:
        return RuleResult("MONOLITH", "FAIL", f"cross_area_threshold:areas={sorted(areas)}")
    for path in targets:
        posix = PurePosixPath(path)
        has_bad_dir = any(part in CATCHALL_DIRS for part in posix.parts[:-1])
        if posix.name in CATCHALL_BASENAMES or has_bad_dir:
            return RuleResult("MONOLITH", "FAIL", f"catchall_forbidden:{path}")
        old = baseline.get(path)
        new = (root / path).read_text(encoding="utf-8")
        new_loc, new_imports, new_exports = _counts(path, new)
        if old is None:
            if new_loc > 400 or new_exports > 25 or new_imports > 15:
                return RuleResult("MONOLITH", "FAIL", f"new_file_limits:{path}")
            continue
        old_loc, old_imports, old_exports = _counts(path, old.decode("utf-8"))
        d_loc = new_loc - old_loc
        d_imports = new_imports - old_imports
        d_exports = new_exports - old_exports
        grew = any(value > 0 for value in (d_loc, d_imports, d_exports))
        if old_loc >= 1300 and grew:
            return RuleResult("MONOLITH", "FAIL", f"huge_file_growth:{path}")
        if old_loc >= 900 and (d_loc > 20 or d_exports > 2 or d_imports > 1):
            return RuleResult("MONOLITH", "FAIL", f"large_file_growth:{path}")
        if d_loc >= 100 and d_exports >= 3 and d_imports >= 5:
            return RuleResult("MONOLITH", "FAIL", f"hub_signal:{path}")
    return RuleResult("MONOLITH", "PASS", "gate_passed")


def _format(results: list[RuleResult]) -> str:
    overall = "FAIL" if any(item.status == "FAIL" for item in results) else "PASS"
    lines = [f"RESULT: {overall}"]
    lines.extend(f"RULE {item.rule_id}: {item.status} - {item.detail}" for item in results)
    return "\n".join(lines) + "\n"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Single-file PM validator for patch artifacts.")
    parser.add_argument("issue_id")
    parser.add_argument("commit_message")
    parser.add_argument("patch")
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
        if args.repair_overlay:
            if not Path(args.repair_overlay).is_file():
                raise ValidationError("repair_overlay_not_found")
        elif not args.workspace_snapshot:
            raise ValidationError("workspace_snapshot_required_for_initial_mode")
        if args.supplemental_file and not args.repair_overlay:
            raise ValidationError("supplemental_file_requires_repair_mode")
        patch_path = Path(args.patch).resolve()
        results = [_validate_basename(patch_path, args.issue_id)]
        more, patch_members, decision_paths = _collect_patch_members(
            patch_path,
            args.issue_id,
            args.commit_message,
        )
        results.extend(more)
        if any(item.status == "FAIL" for item in results):
            sys.stdout.write(_format(results))
            return 1
        results.append(_docs_gate(decision_paths))
        baseline, _mode = _authority_files(args, decision_paths)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_tree(root, baseline)
            results.extend(_apply_patches(root, patch_members))
            if any(item.status == "FAIL" for item in results):
                sys.stdout.write(_format(results))
                return 1
            results.extend(
                [
                    _compile_python(root, decision_paths),
                    _check_js(root, decision_paths),
                    _monolith(root, baseline, decision_paths),
                ]
            )
        sys.stdout.write(_format(results))
        return 0 if all(item.status != "FAIL" for item in results) else 1
    except ValidationError as exc:
        sys.stdout.write(_format([RuleResult("VALIDATION_ERROR", "FAIL", str(exc))]))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
