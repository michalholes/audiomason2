import json
import sys
from collections import defaultdict

FORBIDDEN_FIELDS = {
    "derivation",
    "generated_from",
    "generation_policy",
    "source_line",
}
SUPPORTED_TYPES = {
    "meta",
    "binding_meta",
    "obligation_binding",
    "rule",
    "capability",
    "provider",
    "route",
    "surface",
    "implementation",
}
SUPPORTED_BINDING_TYPES = {
    "resolver_contract",
    "constraint_pack",
}
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


def load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main(path):
    objs = load(path)
    if not objs or objs[0].get("type") != "meta":
        raise SystemExit("FAIL: first object must be meta")

    rules = {}
    caps = {}
    providers = {}
    routes = {}
    surfaces = {}
    impls = {}
    bindings = {}
    binding_meta = None

    for obj in objs:
        obj_type = obj.get("type")
        if obj_type == "source_line":
            raise SystemExit("FAIL: source_line objects are not allowed in v2.0.0")

        for field in FORBIDDEN_FIELDS:
            if field in obj:
                raise SystemExit(
                    f"FAIL forbidden field '{field}' present in {obj.get('id')}"
                )

        if obj_type not in SUPPORTED_TYPES:
            raise SystemExit(f"FAIL unsupported object type {obj_type}")

        if obj_type == "rule":
            rules[obj["id"]] = obj
        elif obj_type == "capability":
            caps[obj["id"]] = obj
        elif obj_type == "provider":
            providers[obj["id"]] = obj
        elif obj_type == "route":
            routes[obj["id"]] = obj
        elif obj_type == "surface":
            surfaces[obj["id"]] = obj
        elif obj_type == "implementation":
            impls[obj["id"]] = obj
        elif obj_type == "binding_meta":
            if binding_meta is not None:
                raise SystemExit("FAIL: exactly one binding_meta object is required")
            binding_meta = obj
        elif obj_type == "obligation_binding":
            binding_id = obj.get("id")
            if binding_id in bindings:
                raise SystemExit(f"FAIL duplicate binding id {binding_id}")
            for field in BINDING_REQUIRED_FIELDS:
                if field not in obj:
                    raise SystemExit(
                        f"FAIL binding {binding_id} missing field {field}"
                    )
            if obj["binding_type"] not in SUPPORTED_BINDING_TYPES:
                raise SystemExit(
                    f"FAIL binding {binding_id} has unsupported binding_type "
                    f"{obj['binding_type']}"
                )
            for field in (
                "verification_mode",
                "verification_method",
                "semantic_group",
                "conflict_policy",
            ):
                if not str(obj.get(field, "")).strip():
                    raise SystemExit(
                        f"FAIL binding {binding_id} has empty field {field}"
                    )
            bindings[binding_id] = obj

    if binding_meta is None:
        raise SystemExit("FAIL: exactly one binding_meta object is required")

    rule_refs: defaultdict[str, int] = defaultdict(int)
    for capability_id, capability in caps.items():
        for rule_id in capability.get("triggers_rules", []):
            if rule_id not in rules:
                raise SystemExit(
                    f"FAIL capability {capability_id} references missing rule {rule_id}"
                )
            rule_refs[rule_id] += 1

    for rule_id in rules:
        if rule_refs[rule_id] == 0:
            raise SystemExit(f"FAIL orphan rule {rule_id}")

    cap_route_refs: defaultdict[str, int] = defaultdict(int)
    for route_id, route in routes.items():
        for capability_id in route.get("covers_capabilities", []):
            if capability_id not in caps:
                raise SystemExit(
                    f"FAIL route {route_id} references missing capability {capability_id}"
                )
            cap_route_refs[capability_id] += 1

    for capability_id, capability in caps.items():
        if not capability.get("triggers_rules"):
            raise SystemExit(f"FAIL capability without rules {capability_id}")
        if cap_route_refs[capability_id] == 0:
            raise SystemExit(
                f"FAIL capability not covered by any route {capability_id}"
            )

    for surface_id, surface in surfaces.items():
        if not surface.get("route_ref"):
            raise SystemExit(f"FAIL surface without route_ref {surface_id}")
        if not surface.get("requires_capabilities"):
            raise SystemExit(
                f"FAIL surface without requires_capabilities {surface_id}"
            )

    for route_id, route in routes.items():
        chain = route.get("provider_chain", [])
        caps_needed = set(route.get("covers_capabilities", []))
        provided = set()
        seen = set()
        for provider_id in chain:
            if provider_id in seen:
                raise SystemExit(
                    "FAIL route "
                    f"{route_id} provider_chain contains duplicate provider "
                    f"{provider_id}"
                )
            seen.add(provider_id)
            if provider_id not in providers:
                raise SystemExit(
                    f"FAIL route {route_id} references missing provider {provider_id}"
                )
            provided |= set(providers[provider_id].get("provides_capabilities", []))

        if not caps_needed.issubset(provided):
            missing = caps_needed - provided
            raise SystemExit(
                f"FAIL provider coverage in route {route_id} missing {sorted(missing)}"
            )

    for implementation_id, implementation in impls.items():
        route_id = implementation.get("implements_route")
        if route_id not in routes:
            raise SystemExit(
                "FAIL implementation "
                f"{implementation_id} references missing route {route_id}"
            )

        required = set(routes[route_id].get("covers_capabilities", []))
        declared = set(implementation.get("declared_capabilities", []))
        if not required.issubset(declared):
            missing = required - declared
            raise SystemExit(
                "FAIL implementation "
                f"{implementation_id} missing capabilities {sorted(missing)}"
            )

    print("V2.0.0 STRICT VALIDATION OK")
    print(
        f"rules={len(rules)} caps={len(caps)} "
        f"providers={len(providers)} routes={len(routes)} "
        f"surfaces={len(surfaces)} impls={len(impls)} "
        f"binding_meta={1 if binding_meta else 0} bindings={len(bindings)}"
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python validate_master_spec_v2.py <jsonl>")
        sys.exit(1)
    main(sys.argv[1])
