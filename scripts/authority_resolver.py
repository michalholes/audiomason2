import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

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


def stop(code, detail):
    raise SystemExit(f"STOP.{code}: {detail}")


def load_jsonl(path):
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def spec_path_from(workspace_path):
    spec_path = workspace_path / "docs" / "specification.jsonl"
    if not spec_path.is_file():
        stop("MISSING_BINDING", f"missing spec file {spec_path}")
    return spec_path


def collect_bindings(objects):
    binding_meta = None
    bindings = []
    for obj in objects:
        obj_type = obj.get("type")
        if obj_type == "binding_meta":
            if binding_meta is not None:
                stop("CONFLICTING_OBLIGATIONS", "multiple binding_meta objects")
            binding_meta = obj
        if obj_type != "obligation_binding":
            continue
        binding_id = obj.get("id", "<missing-id>")
        for field in REQUIRED_FIELDS:
            if field not in obj:
                stop("MISSING_VERIFICATION_CONTRACT", f"{binding_id} missing {field}")
        if obj["binding_type"] not in SUPPORTED_BINDING_TYPES:
            detail = f"{binding_id} unsupported binding_type {obj['binding_type']}"
            stop("CONFLICTING_OBLIGATIONS", detail)
        if not str(obj.get("verification_mode", "")).strip():
            stop("MISSING_VERIFICATION_CONTRACT", f"{binding_id} empty mode")
        if not str(obj.get("verification_method", "")).strip():
            stop("MISSING_VERIFICATION_CONTRACT", f"{binding_id} empty method")
        bindings.append(obj)
    if binding_meta is None:
        stop("MISSING_BINDING", "missing binding_meta object")
    return binding_meta, bindings


def is_active(binding, mode, target_scope):
    match = binding.get("match", {})
    if binding["binding_type"] == "constraint_pack":
        return True
    return match.get("phase") == mode and match.get("target") == target_scope


def ensure_consistency(active_bindings):
    if not active_bindings:
        stop("MISSING_BINDING", "no active bindings for requested scope")
    symbol_matches = defaultdict(list)
    semantics = defaultdict(list)
    role_semantics = defaultdict(set)
    for binding in active_bindings:
        binding_id = binding["id"]
        match_key = json.dumps(binding.get("match", {}), sort_keys=True)
        symbol_key = (match_key, binding["symbol_role"])
        symbol_matches[symbol_key].append(binding_id)
        semantics[binding["authoritative_semantics"]].append(binding_id)
        role_semantics[binding["symbol_role"]].add(binding["authoritative_semantics"])
    for ids in symbol_matches.values():
        if len(ids) > 1:
            stop("AMBIGUOUS_SYMBOL", ", ".join(sorted(ids)))
    for ids in semantics.values():
        if len(ids) > 1:
            stop("DUPLICATE_SEMANTICS", ", ".join(sorted(ids)))
    for role, values in role_semantics.items():
        if len(values) > 1:
            stop("CONFLICTING_OBLIGATIONS", role)


def build_pack(spec_path, mode, target_scope):
    objects = load_jsonl(spec_path)
    if not objects or objects[0].get("type") != "meta":
        stop("MISSING_BINDING", "spec meta object missing")
    binding_meta, bindings = collect_bindings(objects)
    active_bindings = [b for b in bindings if is_active(b, mode, target_scope)]
    ensure_consistency(active_bindings)
    spec_fingerprint = hashlib.sha256(spec_path.read_bytes()).hexdigest()
    active_rule_ids = [binding["id"] for binding in active_bindings]
    pack = {
        "target_symbol": None,
        "target_scope": target_scope,
        "mode": mode,
        "spec_fingerprint": spec_fingerprint,
        "binding_meta_id": binding_meta["id"],
        "active_bindings": active_bindings,
        "active_rule_ids": active_rule_ids,
        "full_rule_text": {
            binding["id"]: binding["authoritative_semantics"]
            for binding in active_bindings
        },
        "match_basis": {
            binding["id"]: binding.get("match", {})
            for binding in active_bindings
        },
        "authoritative_sources": ["docs/specification.jsonl"],
        "shared_contracts": sorted(
            {
                ref
                for binding in active_bindings
                for ref in binding.get("shared_contract_refs", [])
            }
        ),
        "downstream_consumers": sorted(
            {
                consumer
                for binding in active_bindings
                for consumer in binding.get("downstream_consumers", [])
            }
        ),
        "exception_state_refs": sorted(
            {
                ref
                for binding in active_bindings
                for ref in binding.get("exception_state_refs", [])
            }
        ),
        "required_wiring": sorted(
            {
                item
                for binding in active_bindings
                for item in binding.get("required_wiring", [])
            }
        ),
        "forbidden_strategies": sorted(
            {
                item
                for binding in active_bindings
                for item in binding.get("forbidden", [])
            }
        ),
        "required_validation": sorted(
            {
                item
                for binding in active_bindings
                for item in binding.get("required_validation", [])
            }
        ),
        "verification_mode_per_rule": {
            binding["id"]: binding["verification_mode"]
            for binding in active_bindings
        },
        "verification_method_per_rule": {
            binding["id"]: binding["verification_method"]
            for binding in active_bindings
        },
        "oracle_refs": {
            binding["id"]: binding.get("oracle_ref")
            for binding in active_bindings
        },
        "aggregate_scope_metadata": {
            "binding_count": len(active_bindings),
            "mode": mode,
            "target_scope": target_scope,
        },
    }
    pack_json = json.dumps(pack, indent=2, sort_keys=True, ensure_ascii=True)
    pack_bytes = (pack_json + "\n").encode("utf-8")
    hash_value = hashlib.sha256(pack_bytes).hexdigest()
    return pack_bytes, hash_value


def write_outputs(output_dir, pack_bytes, hash_value):
    output_dir.mkdir(parents=True, exist_ok=True)
    pack_path = output_dir / "constraint_pack.json"
    hash_path = output_dir / "hash_pack.txt"
    if pack_path.exists() and pack_path.read_bytes() != pack_bytes:
        stop("PACK_RECOMPUTE_MISMATCH", str(pack_path))
    if hash_path.exists() and hash_path.read_text(encoding="utf-8") != hash_value:
        stop("PACK_RECOMPUTE_MISMATCH", str(hash_path))
    pack_path.write_bytes(pack_bytes)
    hash_path.write_text(hash_value, encoding="utf-8")
    print(f"OK constraint_pack.json {pack_path}")
    print(f"OK hash_pack.txt {hash_path}")


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("discovery", "final"))
    parser.add_argument("workspace_path")
    parser.add_argument("target_scope")
    parser.add_argument("output_dir")
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    workspace_path = Path(args.workspace_path).resolve()
    spec_path = spec_path_from(workspace_path)
    pack_bytes, hash_value = build_pack(spec_path, args.mode, args.target_scope)
    write_outputs(Path(args.output_dir).resolve(), pack_bytes, hash_value)


if __name__ == "__main__":
    main(sys.argv[1:])
