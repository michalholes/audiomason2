from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import tomllib


@dataclass(frozen=True)
class BdgAssetEntry:
    name: str
    content: str


@dataclass(frozen=True)
class BdgAsset:
    asset_id: str
    kind: str
    content: Optional[str]
    entries: List[BdgAssetEntry]


@dataclass(frozen=True)
class BdgStep:
    op: str
    params: Dict[str, Any]


@dataclass(frozen=True)
class BdgTest:
    test_id: str
    makes_commit: bool
    is_guard: bool
    assets: Dict[str, BdgAsset]
    steps: List[BdgStep]


def _as_str(d: dict, key: str, default: str = "") -> str:
    v = d.get(key, default)
    if not isinstance(v, str):
        raise SystemExit(f"FAIL: bdg: key '{key}' must be a string")
    return v


def _as_bool(d: dict, key: str, default: bool = False) -> bool:
    v = d.get(key, default)
    if not isinstance(v, bool):
        raise SystemExit(f"FAIL: bdg: key '{key}' must be a bool")
    return v


def load_bdg_test(path: Path) -> BdgTest:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    meta = raw.get("meta", {})
    if meta is None:
        meta = {}
    if not isinstance(meta, dict):
        raise SystemExit("FAIL: bdg: [meta] must be a table")

    makes_commit = _as_bool(meta, "makes_commit", False)
    is_guard = _as_bool(meta, "is_guard", False)

    assets: Dict[str, BdgAsset] = {}
    for item in raw.get("asset", []):
        if not isinstance(item, dict):
            raise SystemExit("FAIL: bdg: [[asset]] must be a table")
        asset_id = _as_str(item, "id")
        kind = _as_str(item, "kind")
        content = item.get("content")
        if content is not None and not isinstance(content, str):
            raise SystemExit("FAIL: bdg: asset content must be string or omitted")

        entries: List[BdgAssetEntry] = []
        for ent in item.get("entry", []):
            if not isinstance(ent, dict):
                raise SystemExit("FAIL: bdg: [[asset.entry]] must be a table")
            name = _as_str(ent, "name")
            econtent = ent.get("content")
            if not isinstance(econtent, str):
                raise SystemExit("FAIL: bdg: asset.entry content must be string")
            entries.append(BdgAssetEntry(name=name, content=econtent))

        if asset_id in assets:
            raise SystemExit(f"FAIL: bdg: duplicate asset id: {asset_id}")
        assets[asset_id] = BdgAsset(asset_id=asset_id, kind=kind, content=content, entries=entries)

    steps: List[BdgStep] = []
    for item in raw.get("step", []):
        if not isinstance(item, dict):
            raise SystemExit("FAIL: bdg: [[step]] must be a table")
        op = _as_str(item, "op")
        params = dict(item)
        params.pop("op", None)
        steps.append(BdgStep(op=op, params=params))

    if not steps:
        raise SystemExit("FAIL: bdg: must contain at least one [[step]]")

    test_id = path.stem
    return BdgTest(
        test_id=test_id,
        makes_commit=makes_commit,
        is_guard=is_guard,
        assets=assets,
        steps=steps,
    )
