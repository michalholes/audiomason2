from __future__ import annotations

import io
import json
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from badguys.bdg_loader import BdgAsset, BdgTest
from badguys.bdg_recipe import (
    asset_recipe,
    base_cfg_sections,
    ensure_allowed_keys,
    entry_recipe,
    subject_relpaths,
)
from badguys.bdg_subst import SubstCtx, subst_text


@dataclass(frozen=True)
class MaterializedAssets:
    root: Path
    files: dict[str, Path]


def _safe_name(name: str) -> str:
    out = []
    for ch in name:
        if ch.isalnum() or ch in {"_", "-", "."}:
            out.append(ch)
        else:
            out.append("_")
    return "".join(out)


def _build_git_add_file_patch(*, rel_path: str, text: str) -> str:
    if not text.endswith("\n"):
        text += "\n"
    lines = text.splitlines(True)
    body = "".join(["+" + line for line in lines])
    return (
        f"diff --git a/{rel_path} b/{rel_path}\n"
        "new file mode 100644\n"
        "index 0000000..1111111\n"
        "--- /dev/null\n"
        f"+++ b/{rel_path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{body}"
    )


def _subject_relpath(
    *,
    subjects: dict[str, str],
    subject_name: object,
    test_id: str,
    asset_id: str,
    field_name: str,
) -> str:
    if not isinstance(subject_name, str) or not subject_name:
        raise SystemExit(
            f"FAIL: bdg recipe: {test_id}.{asset_id}.{field_name} must be a non-empty string"
        )
    rel_path = subjects.get(subject_name)
    if rel_path is None:
        raise SystemExit(
            f"FAIL: bdg recipe: missing subject '{subject_name}' for {test_id}.{asset_id}"
        )
    return rel_path


def _string_list(
    *,
    value: object,
    test_id: str,
    asset_id: str,
    field_name: str,
) -> list[str]:
    if not (isinstance(value, list) and all(isinstance(item, str) for item in value)):
        raise SystemExit(f"FAIL: bdg recipe: {test_id}.{asset_id}.{field_name} must be list[str]")
    return list(value)


def _build_python_patch_script(
    *,
    body: str,
    issue_id: str,
    subjects: dict[str, str],
    declared_subjects: list[str],
    test_id: str,
    asset_id: str,
) -> str:
    declared_relpaths = [
        _subject_relpath(
            subjects=subjects,
            subject_name=name,
            test_id=test_id,
            asset_id=asset_id,
            field_name="declared_subjects",
        )
        for name in declared_subjects
    ]
    subjects_json = json.dumps(subjects, sort_keys=True)
    files_json = json.dumps(declared_relpaths)
    issue_json = json.dumps(issue_id)
    script_json = json.dumps(body)
    return (
        "from __future__ import annotations\n\n"
        f"FILES = {files_json}\n\n"
        "from pathlib import Path\n\n"
        "REPO = Path(__file__).resolve().parents[1]\n"
        f"_SUBJECTS = {subjects_json}\n"
        f"_ISSUE_ID = {issue_json}\n"
        f"_SCRIPT = {script_json}\n\n"
        "class _Ctx:\n"
        "    def path(self, name: str) -> Path:\n"
        "        rel = _SUBJECTS.get(name)\n"
        "        if rel is None:\n"
        "            raise KeyError(f'unknown subject: {name}')\n"
        "        return REPO / rel\n\n"
        "    def write_text(self, name: str, text: str) -> None:\n"
        "        path = self.path(name)\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(text, encoding='utf-8')\n\n"
        "    def unlink(self, name: str) -> None:\n"
        "        try:\n"
        "            self.path(name).unlink()\n"
        "        except FileNotFoundError:\n"
        "            pass\n\n"
        "    def write_outside_repo(self, text: str) -> None:\n"
        "        outside = (REPO / '..' / f'badguys_sentinel_issue_{_ISSUE_ID}.txt').resolve()\n"
        "        outside.write_text(text, encoding='utf-8')\n\n"
        "ctx = _Ctx()\n"
        "_GLOBALS = {\n"
        "    '__builtins__': __builtins__,\n"
        "    '__file__': str(__file__),\n"
        "    'FILES': FILES,\n"
        "    'Path': Path,\n"
        "    'REPO': REPO,\n"
        "    '_ISSUE_ID': _ISSUE_ID,\n"
        "    '_SUBJECTS': _SUBJECTS,\n"
        "    'ctx': ctx,\n"
        "}\n"
        "exec(compile(_SCRIPT, str(__file__), 'exec'), _GLOBALS, _GLOBALS)\n"
    )


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(base)
    for key, value in override.items():
        current = out.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            out[key] = _deep_merge(current, value)
        else:
            out[key] = value
    return out


def _format_toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_format_toml_value(item) for item in value) + "]"
    raise SystemExit(f"FAIL: bdg materializer: unsupported TOML value: {type(value).__name__}")


def _dump_toml_sections(data: dict[str, Any]) -> str:
    parts: list[str] = []
    for section in ("suite", "lock", "guard", "filters", "runner"):
        table = data.get(section, {})
        if not isinstance(table, dict):
            raise SystemExit(f"FAIL: bdg materializer: section '{section}' must be a table")
        parts.append(f"[{section}]")
        for key in sorted(table.keys()):
            parts.append(f"{key} = {_format_toml_value(table[key])}")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def materialize_assets(
    *,
    repo_root: Path,
    config_path: Path,
    subst: SubstCtx,
    bdg: BdgTest,
) -> MaterializedAssets:
    root = repo_root / "patches" / "badguys_artifacts" / f"issue_{subst.issue_id}" / bdg.test_id
    root.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}
    subjects = subject_relpaths(
        repo_root=repo_root,
        config_path=config_path,
        test_id=bdg.test_id,
    )
    for asset_id, asset in bdg.assets.items():
        files[asset_id] = _materialize_one(
            root=root,
            repo_root=repo_root,
            config_path=config_path,
            subst=subst,
            test_id=bdg.test_id,
            asset=asset,
            subjects=subjects,
        )
    return MaterializedAssets(root=root, files=files)


def _materialize_one(
    *,
    root: Path,
    repo_root: Path,
    config_path: Path,
    subst: SubstCtx,
    test_id: str,
    asset: BdgAsset,
    subjects: dict[str, str],
) -> Path:
    safe_id = _safe_name(asset.asset_id)
    if asset.kind == "text":
        p = root / f"{safe_id}.txt"
        p.write_text(subst_text(asset.content or "", ctx=subst), encoding="utf-8")
        return p

    if asset.kind == "toml_text":
        p = root / f"{safe_id}.toml"
        base = base_cfg_sections(repo_root=repo_root, config_path=config_path)
        delta_raw = subst_text(asset.content or "", ctx=subst)
        delta = tomllib.loads(delta_raw) if delta_raw.strip() else {}
        if not isinstance(delta, dict):
            raise SystemExit("FAIL: bdg materializer: toml_text delta must decode to a table")
        merged = _deep_merge(base, delta)
        p.write_text(_dump_toml_sections(merged), encoding="utf-8")
        return p

    if asset.kind == "python_patch_script":
        recipe = asset_recipe(
            repo_root=repo_root,
            config_path=config_path,
            test_id=test_id,
            asset_id=asset.asset_id,
        )
        ensure_allowed_keys(
            table=recipe,
            allowed={"declared_subjects"},
            label=f"recipes.tests.{test_id}.assets.{asset.asset_id}",
        )
        declared_subjects = _string_list(
            value=recipe.get("declared_subjects", []),
            test_id=test_id,
            asset_id=asset.asset_id,
            field_name="declared_subjects",
        )
        patches_dir = repo_root / "patches"
        patches_dir.mkdir(parents=True, exist_ok=True)
        safe_test = _safe_name(test_id)
        p = patches_dir / f"issue_{subst.issue_id}__bdg__{safe_test}__{safe_id}.py"
        body = subst_text(asset.content or "", ctx=subst)
        script = _build_python_patch_script(
            body=body,
            issue_id=subst.issue_id,
            subjects=subjects,
            declared_subjects=declared_subjects,
            test_id=test_id,
            asset_id=asset.asset_id,
        )
        p.write_text(script, encoding="utf-8")
        return p

    if asset.kind == "git_patch_text":
        recipe = asset_recipe(
            repo_root=repo_root,
            config_path=config_path,
            test_id=test_id,
            asset_id=asset.asset_id,
        )
        ensure_allowed_keys(
            table=recipe,
            allowed={"subject"},
            label=f"recipes.tests.{test_id}.assets.{asset.asset_id}",
        )
        rel_path = _subject_relpath(
            subjects=subjects,
            subject_name=recipe.get("subject"),
            test_id=test_id,
            asset_id=asset.asset_id,
            field_name="subject",
        )
        patches_dir = repo_root / "patches"
        patches_dir.mkdir(parents=True, exist_ok=True)
        safe_test = _safe_name(test_id)
        p = patches_dir / f"issue_{subst.issue_id}__bdg__{safe_test}__{safe_id}.patch"
        content = subst_text(asset.content or "", ctx=subst)
        p.write_text(_build_git_add_file_patch(rel_path=rel_path, text=content), encoding="utf-8")
        return p

    if asset.kind == "patch_zip_manifest":
        patches_dir = repo_root / "patches"
        patches_dir.mkdir(parents=True, exist_ok=True)
        safe_test = _safe_name(test_id)
        p = patches_dir / f"issue_{subst.issue_id}__bdg__{safe_test}__{safe_id}.zip"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for ent in asset.entries:
                recipe = entry_recipe(
                    repo_root=repo_root,
                    config_path=config_path,
                    test_id=test_id,
                    asset_id=asset.asset_id,
                    entry_id=ent.name,
                )
                ensure_allowed_keys(
                    table=recipe,
                    allowed={"declared_subjects", "kind", "subject", "zip_name"},
                    label=(f"recipes.tests.{test_id}.assets.{asset.asset_id}.entries.{ent.name}"),
                )
                zip_name = recipe.get("zip_name")
                if not isinstance(zip_name, str) or not zip_name:
                    raise SystemExit(
                        "FAIL: bdg recipe: "
                        f"missing zip_name for {test_id}.{asset.asset_id}.{ent.name}"
                    )
                kind = recipe.get("kind")
                if kind == "git_patch_text":
                    rel_path = _subject_relpath(
                        subjects=subjects,
                        subject_name=recipe.get("subject"),
                        test_id=test_id,
                        asset_id=f"{asset.asset_id}.{ent.name}",
                        field_name="subject",
                    )
                    data = _build_git_add_file_patch(
                        rel_path=rel_path,
                        text=subst_text(ent.content, ctx=subst),
                    ).encode("utf-8")
                elif kind == "python_patch_script":
                    declared_subjects = _string_list(
                        value=recipe.get("declared_subjects", []),
                        test_id=test_id,
                        asset_id=f"{asset.asset_id}.{ent.name}",
                        field_name="declared_subjects",
                    )
                    data = _build_python_patch_script(
                        body=subst_text(ent.content, ctx=subst),
                        issue_id=subst.issue_id,
                        subjects=subjects,
                        declared_subjects=declared_subjects,
                        test_id=test_id,
                        asset_id=f"{asset.asset_id}.{ent.name}",
                    ).encode("utf-8")
                else:
                    raise SystemExit(
                        "FAIL: bdg recipe: unsupported zip entry kind for "
                        f"{test_id}.{asset.asset_id}.{ent.name}"
                    )
                info = zipfile.ZipInfo(zip_name)
                info.date_time = (1980, 1, 1, 0, 0, 0)
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, data)
        p.write_bytes(buf.getvalue())
        return p

    raise SystemExit(f"FAIL: bdg materializer: unsupported asset kind: {asset.kind}")
