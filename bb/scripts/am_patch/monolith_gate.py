from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import RunnerError
from .log import Logger


@dataclass(frozen=True)
class MonolithAreas:
    rel_prefix: str
    area: str
    dynamic: str | None = None


@dataclass(frozen=True)
class FileMetrics:
    loc: int
    exports: int
    internal_imports: int
    distinct_areas: int
    fanin: int | None
    fanout: int | None
    parse_ok: bool


@dataclass(frozen=True)
class Violation:
    rule_id: str
    relpath: str
    message: str
    severity: str  # FAIL|WARN|REPORT


def _norm_relpath(p: str) -> str:
    s = str(p).replace("\\", "/").strip()
    if s.startswith("./"):
        s = s[2:]
    return s.strip("/")


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
    n = 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = getattr(node, "name", "")
            if name and not name.startswith("_"):
                n += 1
    return n


def _iter_import_modules(tree: ast.AST, *, current_module: str | None) -> list[str]:
    out: list[str] = []

    def add(mod: str) -> None:
        s = str(mod).strip().strip(".")
        if s and s not in out:
            out.append(s)

    def resolve_relative(level: int, mod: str | None) -> str | None:
        if not current_module or level <= 0:
            return None
        parts = current_module.split(".")
        # current_module includes the leaf module; treat parent as package for relative imports.
        if parts:
            parts = parts[:-1]
        up = max(0, min(level - 1, len(parts)))
        base = parts[: len(parts) - up]
        if mod:
            m = str(mod).strip(".")
            if not m:
                return ".".join(base) or None
            return ".".join([*base, m]) if base else m
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

    return out


def _areas_from_policy(raw: list[dict[str, str]]) -> list[MonolithAreas]:
    out: list[MonolithAreas] = []
    for item in raw:
        prefix = _norm_relpath(item.get("prefix", ""))
        area = str(item.get("area", "")).strip()
        dyn = str(item.get("dynamic", "")).strip() or None
        if not prefix or not area:
            continue
        out.append(MonolithAreas(rel_prefix=prefix.rstrip("/") + "/", area=area, dynamic=dyn))
    return out


def area_for_relpath(relpath: str, areas: list[MonolithAreas]) -> str:
    rp = _norm_relpath(relpath)
    rp2 = rp + "/" if not rp.endswith("/") else rp
    for a in areas:
        if rp2.startswith(a.rel_prefix):
            if a.dynamic == "plugins.<name>":
                # relpath: plugins/<name>/...
                parts = rp.split("/")
                if len(parts) >= 2 and parts[0] == "plugins":
                    return f"plugins.{parts[1]}"
            return a.area
    return "other"


def _module_for_relpath(relpath: str) -> str | None:
    rp = _norm_relpath(relpath)
    if rp.startswith("src/audiomason/") and rp.endswith(".py"):
        sub = rp[len("src/") : -3].replace("/", ".")
        if sub.endswith(".__init__"):
            sub = sub[: -len(".__init__")]
        return sub
    if rp.startswith("scripts/am_patch/") and rp.endswith(".py"):
        sub = rp[len("scripts/") : -3].replace("/", ".")
        if sub.endswith(".__init__"):
            sub = sub[: -len(".__init__")]
        return sub
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
        if sub.endswith(".__init__"):
            sub = sub[: -len(".__init__")]
        return sub
    return None


def _module_to_rel_hint(mod: str) -> str | None:
    s = str(mod).strip().strip(".")
    if not s:
        return None
    parts = s.split(".")
    if not parts:
        return None
    root = parts[0]
    if root == "audiomason":
        rest = "/".join(parts[1:])
        return ("src/audiomason/" + rest + ".py") if rest else "src/audiomason/__init__.py"
    if root == "am_patch":
        rest = "/".join(parts[1:])
        return ("scripts/am_patch/" + rest + ".py") if rest else "scripts/am_patch/__init__.py"
    if root == "plugins" and len(parts) >= 2:
        name = parts[1]
        rest = "/".join(parts[2:])
        return ("plugins/" + name + "/" + rest + ".py") if rest else ("plugins/" + name + "/__init__.py")
    if root == "tests":
        rest = "/".join(parts[1:])
        return ("tests/" + rest + ".py") if rest else "tests/__init__.py"
    return None


def _area_for_module(mod: str, areas: list[MonolithAreas]) -> str:
    hint = _module_to_rel_hint(mod)
    if not hint:
        return "other"
    # Normalize to a directory hint for area prefix matching.
    area = area_for_relpath(hint, areas)
    if area != "other":
        return area
    # Also allow matching by package prefix (directory) when module points to a submodule file.
    d = _norm_relpath(str(Path(hint).parent))
    if d:
        area2 = area_for_relpath(d + "/x.py", areas)
        if area2 != "other":
            return area2
    return "other"



def _is_catchall_new_file(
    relpath: str,
    *,
    basenames: list[str],
    dirs: list[str],
    allowlist: list[str],
) -> bool:
    rp = _norm_relpath(relpath)
    if rp in set(_norm_relpath(x) for x in allowlist):
        return False
    base = Path(rp).name
    if base in set(basenames):
        return True
    parts = [p for p in rp.split("/") if p]
    if any(seg in set(dirs) for seg in parts[:-1]):
        return True
    return False


def _tier(loc: int, *, large: int, huge: int) -> str:
    if loc >= huge:
        return "huge"
    if loc >= large:
        return "large"
    return "normal"


def _scan_candidates(
    cwd: Path,
    *,
    decision_paths: list[str],
    scope: str,
    areas: list[MonolithAreas],
) -> list[str]:
    if scope == "patch":
        out: list[str] = []
        for p in decision_paths:
            rp = _norm_relpath(p)
            if not rp.endswith(".py"):
                continue
            if (cwd / rp).exists() and rp not in out:
                out.append(rp)
        out.sort()
        return out

    if scope == "workspace":
        prefixes = [a.rel_prefix for a in areas]
        out_set: set[str] = set()
        for pref in prefixes:
            root = cwd / pref.rstrip("/")
            if not root.exists():
                continue
            for f in sorted(root.rglob("*.py")):
                if f.is_file():
                    out_set.add(_norm_relpath(str(f.relative_to(cwd))))
        out = sorted(out_set)
        return out

    raise RunnerError("GATES", "MONOLITH", f"invalid gate_monolith_scan_scope={scope!r}")


def _fan_graph(
    root: Path,
    *,
    relpaths: list[str],
) -> tuple[dict[str, int], dict[str, int]]:
    # Build fanin/fanout based on internal imports among relpaths.
    module_to_rel: dict[str, str] = {}
    rel_to_module: dict[str, str] = {}
    for rp in relpaths:
        m = _module_for_relpath(rp)
        if m:
            module_to_rel[m] = rp
            rel_to_module[rp] = m

    def resolve_target(mod: str) -> str | None:
        s = str(mod).strip().strip(".")
        if not s:
            return None
        cur = s
        while True:
            if cur in module_to_rel:
                return module_to_rel[cur]
            if "." not in cur:
                return None
            cur = cur.rsplit(".", 1)[0]

    edges: dict[str, set[str]] = {rp: set() for rp in relpaths}
    for rp in relpaths:
        path = root / rp
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        tree = _parse_tree(text)
        if tree is None:
            continue
        cur_mod = rel_to_module.get(rp)
        for mod in _iter_import_modules(tree, current_module=cur_mod):
            tgt = resolve_target(mod)
            if tgt and tgt != rp:
                edges[rp].add(tgt)

    fanout: dict[str, int] = {rp: len(edges[rp]) for rp in relpaths}
    fanin: dict[str, int] = {rp: 0 for rp in relpaths}
    for src, tgts in edges.items():
        for tgt in tgts:
            fanin[tgt] = fanin.get(tgt, 0) + 1

    return fanin, fanout


def _analyze_file(
    *,
    relpath: str,
    text: str,
    areas: list[MonolithAreas],
    fanin: int | None,
    fanout: int | None,
) -> FileMetrics:
    tree = _parse_tree(text)
    if tree is None:
        return FileMetrics(
            loc=_count_loc(text),
            exports=0,
            internal_imports=0,
            distinct_areas=0,
            fanin=fanin,
            fanout=fanout,
            parse_ok=False,
        )

    exports = _count_exports(tree)
    cur_mod = _module_for_relpath(relpath)
    mods = _iter_import_modules(tree, current_module=cur_mod)

    internal_mods: set[str] = set()
    imported_areas: set[str] = set()
    for m in mods:
        area = _area_for_module(m, areas)
        if area == "other":
            continue
        internal_mods.add(m)
        imported_areas.add(area)

    return FileMetrics(
        loc=_count_loc(text),
        exports=exports,
        internal_imports=len(internal_mods),
        distinct_areas=len(imported_areas),
        fanin=fanin,
        fanout=fanout,
        parse_ok=True,
    )


def run_monolith_gate(
    logger: Logger,
    cwd: Path,
    *,
    repo_root: Path,
    decision_paths: list[str],
    gate_monolith_mode: str,
    gate_monolith_scan_scope: str,
    gate_monolith_compute_fanin: bool,
    gate_monolith_on_parse_error: str,
    gate_monolith_areas: list[dict[str, str]],
    gate_monolith_large_loc: int,
    gate_monolith_huge_loc: int,
    gate_monolith_large_allow_loc_increase: int,
    gate_monolith_huge_allow_loc_increase: int,
    gate_monolith_large_allow_exports_delta: int,
    gate_monolith_huge_allow_exports_delta: int,
    gate_monolith_large_allow_imports_delta: int,
    gate_monolith_huge_allow_imports_delta: int,
    gate_monolith_new_file_max_loc: int,
    gate_monolith_new_file_max_exports: int,
    gate_monolith_new_file_max_imports: int,
    gate_monolith_hub_fanin_delta: int,
    gate_monolith_hub_fanout_delta: int,
    gate_monolith_hub_exports_delta_min: int,
    gate_monolith_hub_loc_delta_min: int,
    gate_monolith_crossarea_min_distinct_areas: int,
    gate_monolith_catchall_basenames: list[str],
    gate_monolith_catchall_dirs: list[str],
    gate_monolith_catchall_allowlist: list[str],
) -> bool:
    if gate_monolith_mode not in ("strict", "warn_only", "report_only"):
        raise RunnerError(
            "CONFIG",
            "INVALID",
            f"invalid gate_monolith_mode={gate_monolith_mode!r}; allowed: strict|warn_only|report_only",
        )
    if gate_monolith_on_parse_error not in ("fail", "warn"):
        raise RunnerError(
            "CONFIG",
            "INVALID",
            (
                "invalid gate_monolith_on_parse_error="
                f"{gate_monolith_on_parse_error!r}; allowed: fail|warn"
            ),
        )

    areas = _areas_from_policy(gate_monolith_areas)
    candidates = _scan_candidates(
        cwd,
        decision_paths=decision_paths,
        scope=gate_monolith_scan_scope,
        areas=areas,
    )

    logger.section("GATE: MONOLITH")
    logger.line("gate_monolith_mode=" + gate_monolith_mode)
    logger.line("gate_monolith_scan_scope=" + gate_monolith_scan_scope)
    logger.line("gate_monolith_candidates=" + str(len(candidates)))

    fanin_map: dict[str, int] = {}
    fanout_map: dict[str, int] = {}
    fanin_map_old: dict[str, int] = {}
    fanout_map_old: dict[str, int] = {}
    if gate_monolith_compute_fanin and candidates:
        fanin_map, fanout_map = _fan_graph(cwd, relpaths=candidates)
        fanin_map_old, fanout_map_old = _fan_graph(repo_root, relpaths=candidates)

    violations: list[Violation] = []

    def add(rule_id: str, relpath: str, msg: str, sev: str) -> None:
        violations.append(Violation(rule_id=rule_id, relpath=relpath, message=msg, severity=sev))

    for rp in candidates:
        new_path = cwd / rp
        old_path = repo_root / rp
        is_new_file = not old_path.exists()

        new_text = new_path.read_text(encoding="utf-8")
        old_text = old_path.read_text(encoding="utf-8") if old_path.exists() else ""

        fanin_new = fanin_map.get(rp) if gate_monolith_compute_fanin else None
        fanout_new = fanout_map.get(rp) if gate_monolith_compute_fanin else None
        fanin_old = fanin_map_old.get(rp) if gate_monolith_compute_fanin else None
        fanout_old = fanout_map_old.get(rp) if gate_monolith_compute_fanin else None

        new_m = _analyze_file(
            relpath=rp,
            text=new_text,
            areas=areas,
            fanin=fanin_new,
            fanout=fanout_new,
        )

        old_m = _analyze_file(
            relpath=rp,
            text=old_text,
            areas=areas,
            fanin=None,
            fanout=None,
        )

        loc_delta = new_m.loc - old_m.loc
        exp_delta = new_m.exports - old_m.exports
        imp_delta = new_m.internal_imports - old_m.internal_imports

        tier = _tier(new_m.loc, large=gate_monolith_large_loc, huge=gate_monolith_huge_loc)
        allow_loc = (
            gate_monolith_huge_allow_loc_increase
            if tier == "huge"
            else gate_monolith_large_allow_loc_increase
            if tier == "large"
            else None
        )
        allow_exp = (
            gate_monolith_huge_allow_exports_delta
            if tier == "huge"
            else gate_monolith_large_allow_exports_delta
            if tier == "large"
            else None
        )
        allow_imp = (
            gate_monolith_huge_allow_imports_delta
            if tier == "huge"
            else gate_monolith_large_allow_imports_delta
            if tier == "large"
            else None
        )

        # MONO.PARSE
        if not new_m.parse_ok or (old_path.exists() and not old_m.parse_ok):
            sev = "FAIL" if gate_monolith_on_parse_error == "fail" else "WARN"
            add(
                "MONO.PARSE",
                rp,
                f"ast_parse_failed on={'new' if not new_m.parse_ok else 'old'}",
                sev,
            )

        file_area = area_for_relpath(rp, areas)

        # MONO.CATCHALL
        if is_new_file and _is_catchall_new_file(
            rp,
            basenames=gate_monolith_catchall_basenames,
            dirs=gate_monolith_catchall_dirs,
            allowlist=gate_monolith_catchall_allowlist,
        ):
            add("MONO.CATCHALL", rp, "new_catchall_file", "FAIL")

        # MONO.NEWFILE
        if is_new_file:
            if new_m.loc > gate_monolith_new_file_max_loc:
                add(
                    "MONO.NEWFILE",
                    rp,
                    f"loc={new_m.loc} > max={gate_monolith_new_file_max_loc}",
                    "FAIL",
                )
            if new_m.exports > gate_monolith_new_file_max_exports:
                add(
                    "MONO.NEWFILE",
                    rp,
                    f"exports={new_m.exports} > max={gate_monolith_new_file_max_exports}",
                    "FAIL",
                )
            if new_m.internal_imports > gate_monolith_new_file_max_imports:
                add(
                    "MONO.NEWFILE",
                    rp,
                    (
                        "internal_imports="
                        f"{new_m.internal_imports} > max={gate_monolith_new_file_max_imports}"
                    ),
                    "FAIL",
                )

        # MONO.GROWTH
        if tier in ("large", "huge") and allow_loc is not None and allow_exp is not None:
            if loc_delta > allow_loc:
                add(
                    "MONO.GROWTH",
                    rp,
                    f"tier={tier} loc_delta={loc_delta} allow={allow_loc}",
                    "FAIL",
                )
            if exp_delta > allow_exp:
                add(
                    "MONO.GROWTH",
                    rp,
                    f"tier={tier} exports_delta={exp_delta} allow={allow_exp}",
                    "FAIL",
                )
            if allow_imp is not None and imp_delta > allow_imp:
                add(
                    "MONO.GROWTH",
                    rp,
                    f"tier={tier} imports_delta={imp_delta} allow={allow_imp}",
                    "FAIL",
                )

        # MONO.CORE
        if file_area == "core":
            cur_mod = _module_for_relpath(rp)
            mods = []
            tree = _parse_tree(new_text)
            if tree is not None:
                mods = _iter_import_modules(tree, current_module=cur_mod)
            imported_areas = {_area_for_module(m, areas) for m in mods}
            if any(a.startswith("plugins.") for a in imported_areas) or "runner" in imported_areas:
                add("MONO.CORE", rp, "core_imports_plugins_or_runner", "FAIL")

        # MONO.CROSSAREA
        if (
            new_m.distinct_areas >= gate_monolith_crossarea_min_distinct_areas
            and (loc_delta > 0 or exp_delta > 0)
        ):
            add(
                "MONO.CROSSAREA",
                rp,
                f"distinct_areas={new_m.distinct_areas} delta_loc={loc_delta} delta_exports={exp_delta}",
                "FAIL" if gate_monolith_mode == "strict" else "WARN",
            )


        # MONO.HUB
        if (
            gate_monolith_compute_fanin
            and fanin_new is not None
            and fanout_new is not None
            and fanin_old is not None
            and fanout_old is not None
        ):
            fanin_delta = fanin_new - fanin_old
            fanout_delta = fanout_new - fanout_old
            if (
                fanin_delta >= gate_monolith_hub_fanin_delta
                and exp_delta >= gate_monolith_hub_exports_delta_min
            ):
                add(
                    "MONO.HUB",
                    rp,
                    f"fanin_delta={fanin_delta} exports_delta={exp_delta}",
                    "FAIL" if gate_monolith_mode == "strict" else "WARN",
                )
            if (
                fanout_delta >= gate_monolith_hub_fanout_delta
                and loc_delta >= gate_monolith_hub_loc_delta_min
            ):
                add(
                    "MONO.HUB",
                    rp,
                    f"fanout_delta={fanout_delta} loc_delta={loc_delta}",
                    "FAIL" if gate_monolith_mode == "strict" else "WARN",
                )
        
    # Map severities by mode.
    mapped: list[Violation] = []
    for v in violations:
        sev = v.severity
        if gate_monolith_mode == "report_only":
            sev = "REPORT"
        elif gate_monolith_mode == "warn_only":
            if v.rule_id in ("MONO.CORE", "MONO.CATCHALL"):
                sev = "FAIL"
            elif sev == "FAIL":
                sev = "WARN"
        mapped.append(Violation(rule_id=v.rule_id, relpath=v.relpath, message=v.message, severity=sev))

    # Emit.
    fail = [v for v in mapped if v.severity == "FAIL"]
    warn = [v for v in mapped if v.severity in ("WARN", "REPORT")]

    for v in sorted(mapped, key=lambda x: (x.rule_id, x.relpath)):
        line = f"{v.rule_id} {v.relpath} {v.severity} {v.message}"
        if v.severity == "FAIL":
            logger.error_core(line)
        elif v.severity == "WARN":
            logger.warning_core(line)
        else:
            logger.line(line)

    if fail:
        logger.error_core("MONOLITH: FAIL")
        return False
    if warn:
        logger.warning_core("MONOLITH: WARN")
        return True

    logger.line("MONOLITH: PASS")
    return True
