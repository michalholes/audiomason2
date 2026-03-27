import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

REQUIRED_FIELDS = (
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
SUPPORTED_BINDING_TYPES = {"resolver_contract", "constraint_pack"}


def fail(code: str, detail: str) -> None:
    print("RESULT: FAIL")
    print(f"RULE {code}: FAIL - {detail}")
    raise SystemExit(1)


def load_snapshot_entries(path: Path) -> dict[str, bytes]:
    with ZipFile(path, "r") as zf:
        return {name: zf.read(name) for name in zf.namelist() if not name.endswith("/")}


def load_spec(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def split_target(raw: str) -> tuple[str, str | None]:
    repo_path, sep, symbol = raw.partition("::")
    if not repo_path.strip():
        fail("AMBIGUOUS_TARGET", "empty repo path")
    return repo_path.strip(), symbol.strip() if sep else None


def resolve_target(entries: dict[str, bytes], repo_path: str, symbol: str | None) -> None:
    raw = entries.get(repo_path)
    if raw is None:
        fail("MISSING_AUTHORITY", f"missing target {repo_path}")
    if symbol is None:
        return
    text = raw.decode("utf-8", errors="ignore")
    hits = text.count(symbol)
    if hits == 0:
        fail("MISSING_AUTHORITY", f"missing symbol {symbol}")
    if hits > 1:
        fail("AMBIGUOUS_TARGET", f"symbol {symbol} appears {hits} times")


def target_scope(repo_path: str) -> str:
    if repo_path.startswith(("docs/", "scripts/")):
        return "authority_scope"
    return "implementation_scope"


def collect_bindings(objects: list[dict]) -> tuple[dict, list[dict]]:
    binding_meta = None
    bindings = []
    for obj in objects:
        obj_type = obj.get("type")
        if obj_type == "binding_meta":
            if binding_meta is not None:
                fail("CONFLICTING_OBLIGATIONS", "multiple binding_meta objects")
            binding_meta = obj
        if obj_type != "obligation_binding":
            continue
        binding_id = obj.get("id", "<missing-id>")
        for field in REQUIRED_FIELDS:
            if field not in obj:
                fail(
                    "MISSING_VERIFICATION_CONTRACT",
                    f"{binding_id} missing field {field}",
                )
        if obj["binding_type"] not in SUPPORTED_BINDING_TYPES:
            detail = f"{binding_id} unsupported type {obj['binding_type']}"
            fail("CONFLICTING_OBLIGATIONS", detail)
        for field in (
            "verification_mode",
            "verification_method",
            "semantic_group",
            "conflict_policy",
        ):
            if not str(obj.get(field, "")).strip():
                fail("MISSING_VERIFICATION_CONTRACT", f"{binding_id} empty {field}")
        bindings.append(obj)
    if binding_meta is None:
        fail("MISSING_BINDING", "missing binding_meta object")
    return binding_meta, bindings


def active_bindings(bindings: list[dict], scope: str) -> list[dict]:
    active: list[dict] = []
    for binding in bindings:
        match = binding.get("match", {})
        if binding["binding_type"] == "constraint_pack":
            active.append(binding)
            continue
        if match.get("target") == scope:
            active.append(binding)
    return active


def ensure_consistency(bindings: list[dict]) -> None:
    if not bindings:
        fail("MISSING_BINDING", "no active bindings for requested scope")
    symbol_matches: dict[tuple[str, str], list[str]] = defaultdict(list)
    semantics: dict[str, list[str]] = defaultdict(list)
    role_semantics: dict[str, set[str]] = defaultdict(set)
    for binding in bindings:
        binding_id = binding["id"]
        match_key = json.dumps(binding.get("match", {}), sort_keys=True)
        symbol_key = (match_key, binding["symbol_role"])
        symbol_matches[symbol_key].append(binding_id)
        semantics[binding["authoritative_semantics"]].append(binding_id)
        role_semantics[binding["symbol_role"]].add(binding["authoritative_semantics"])
    for ids in symbol_matches.values():
        if len(ids) > 1:
            fail("AMBIGUOUS_TARGET", ", ".join(sorted(ids)))
    for ids in semantics.values():
        if len(ids) > 1:
            fail("DUPLICATE_SEMANTICS", ", ".join(sorted(ids)))
    for role, values in role_semantics.items():
        if len(values) > 1:
            fail("CONFLICTING_OBLIGATIONS", role)


def build_pack(
    spec_path: Path,
    target: str,
    repo_path: str,
    symbol: str | None,
    scope: str,
) -> bytes:
    objects = load_spec(spec_path)
    if not objects or objects[0].get("type") != "meta":
        fail("MISSING_BINDING", "spec meta object missing")
    binding_meta, bindings = collect_bindings(objects)
    active = active_bindings(bindings, scope)
    ensure_consistency(active)
    spec_bytes = spec_path.read_bytes()
    pack = {
        "target": target,
        "target_symbol": symbol,
        "target_path": repo_path,
        "target_scope": scope,
        "spec_fingerprint": hashlib.sha256(spec_bytes).hexdigest(),
        "binding_meta_id": binding_meta["id"],
        "active_bindings": active,
        "active_rule_ids": [binding["id"] for binding in active],
        "authoritative_sources": ["docs/specification.jsonl"],
        "shared_contracts": sorted(
            {ref for binding in active for ref in binding["shared_contract_refs"]}
        ),
        "downstream_consumers": sorted(
            {ref for binding in active for ref in binding["downstream_consumers"]}
        ),
        "exception_state_refs": sorted(
            {ref for binding in active for ref in binding["exception_state_refs"]}
        ),
        "required_wiring": sorted(
            {ref for binding in active for ref in binding["required_wiring"]}
        ),
        "required_validation": sorted(
            {ref for binding in active for ref in binding["required_validation"]}
        ),
        "verification_method_per_rule": {
            binding["id"]: binding["verification_method"] for binding in active
        },
        "verification_mode_per_rule": {
            binding["id"]: binding["verification_mode"] for binding in active
        },
    }
    pack_json = json.dumps(pack, indent=2, sort_keys=True, ensure_ascii=True)
    return (pack_json + "\n").encode("utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    parser.add_argument("--workspace-snapshot", required=True)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--handoff-output", required=True)
    parser.add_argument("--pack-output", required=True)
    parser.add_argument("--hash-output", required=True)
    return parser.parse_args(argv)


def main(argv: list[str]) -> None:
    args = parse_args(argv)
    repo_path, symbol = split_target(args.target)
    entries = load_snapshot_entries(Path(args.workspace_snapshot))
    resolve_target(entries, repo_path, symbol)
    scope = target_scope(repo_path)
    pack_bytes = build_pack(Path(args.spec), args.target, repo_path, symbol, scope)
    handoff_text = "\n".join(
        [
            "SPEC CONTEXT",
            "RC version used: resolver-generated",
            "PM version used: resolver-generated",
            "",
            f"TARGET: {args.target}",
            f"TARGET_SCOPE: {scope}",
        ]
    ) + "\n"
    Path(args.handoff_output).write_text(handoff_text, encoding="utf-8")
    Path(args.pack_output).write_bytes(pack_bytes)
    hash_value = hashlib.sha256(pack_bytes).hexdigest()
    Path(args.hash_output).write_text(hash_value, encoding="utf-8")
    print("RESULT: PASS")


if __name__ == "__main__":
    main(sys.argv[1:])
