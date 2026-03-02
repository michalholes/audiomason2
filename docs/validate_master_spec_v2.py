import json, sys
from collections import defaultdict

FORBIDDEN_FIELDS = {"derivation", "generated_from", "generation_policy", "source_line"}

def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

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

    for o in objs:
        if o.get("type") == "source_line":
            raise SystemExit("FAIL: source_line objects are not allowed in v2.0.0")
        for field in FORBIDDEN_FIELDS:
            if field in o:
                raise SystemExit(f"FAIL forbidden field '{field}' present in {o.get('id')}")

        t = o.get("type")
        if t == "rule": rules[o["id"]] = o
        elif t == "capability": caps[o["id"]] = o
        elif t == "provider": providers[o["id"]] = o
        elif t == "route": routes[o["id"]] = o
        elif t == "surface": surfaces[o["id"]] = o
        elif t == "implementation": impls[o["id"]] = o

    # RULE referenced by >=1 capability
    rule_refs = defaultdict(int)
    for cid, c in caps.items():
        for rid in c.get("triggers_rules", []):
            if rid not in rules:
                raise SystemExit(f"FAIL capability {cid} references missing rule {rid}")
            rule_refs[rid] += 1
    for rid in rules:
        if rule_refs[rid] == 0:
            raise SystemExit(f"FAIL orphan rule {rid}")

    # CAP must have rules and route coverage
    cap_route_refs = defaultdict(int)
    for rid, r in routes.items():
        for cid in r.get("covers_capabilities", []):
            if cid not in caps:
                raise SystemExit(f"FAIL route {rid} references missing capability {cid}")
            cap_route_refs[cid] += 1
    for cid, c in caps.items():
        if not c.get("triggers_rules"):
            raise SystemExit(f"FAIL capability without rules {cid}")
        if cap_route_refs[cid] == 0:
            raise SystemExit(f"FAIL capability not covered by any route {cid}")

    # Surface contract
    for sid, s in surfaces.items():
        if not s.get("route_ref"):
            raise SystemExit(f"FAIL surface without route_ref {sid}")
        if not s.get("requires_capabilities"):
            raise SystemExit(f"FAIL surface without requires_capabilities {sid}")

    # Provider coverage
    for rid, r in routes.items():
        chain = r.get("provider_chain", [])
        caps_needed = set(r.get("covers_capabilities", []))
        provided = set()
        seen = set()
        for pid in chain:
            if pid in seen:
                raise SystemExit(f"FAIL route {rid} provider_chain contains duplicate provider {pid}")
            seen.add(pid)
            if pid not in providers:
                raise SystemExit(f"FAIL route {rid} references missing provider {pid}")
            provided |= set(providers[pid].get("provides_capabilities", []))
        if not caps_needed.issubset(provided):
            missing = caps_needed - provided
            raise SystemExit(f"FAIL provider coverage in route {rid} missing {sorted(missing)}")

    # Implementation coverage (if any)
    for iid, impl in impls.items():
        route_id = impl.get("implements_route")
        if route_id not in routes:
            raise SystemExit(f"FAIL implementation {iid} references missing route {route_id}")
        required = set(routes[route_id].get("covers_capabilities", []))
        declared = set(impl.get("declared_capabilities", []))
        if not required.issubset(declared):
            missing = required - declared
            raise SystemExit(f"FAIL implementation {iid} missing capabilities {sorted(missing)}")

    print("V2.0.0 STRICT VALIDATION OK")
    print(f"rules={len(rules)} caps={len(caps)} providers={len(providers)} routes={len(routes)} surfaces={len(surfaces)} impls={len(impls)}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python validate_master_spec_v2.py <jsonl>")
        sys.exit(1)
    main(sys.argv[1])
