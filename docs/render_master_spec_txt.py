import json
import sys
from pathlib import Path

def load_jsonl(path: Path):
    objs = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                objs.append(json.loads(line))
    return objs

def index_by_type(objs):
    meta = None
    rules = {}
    caps = {}
    providers = {}
    routes = {}
    surfaces = {}
    impls = {}
    others = []

    for o in objs:
        t = o.get("type")
        if t == "meta":
            meta = o
        elif t == "rule":
            rules[o["id"]] = o
        elif t == "capability":
            caps[o["id"]] = o
        elif t == "provider":
            providers[o["id"]] = o
        elif t == "route":
            routes[o["id"]] = o
        elif t == "surface":
            surfaces[o["id"]] = o
        elif t == "implementation":
            impls[o["id"]] = o
        else:
            others.append(o)
    return meta, rules, caps, providers, routes, surfaces, impls, others

def fmt_source(rule):
    ms = rule.get("migration_source")
    if isinstance(ms, dict):
        return f"{ms.get('file','?')}#L{ms.get('line','?')}"
    return ""

def render(path_in: Path, path_out: Path):
    objs = load_jsonl(path_in)
    meta, rules, caps, providers, routes, surfaces, impls, others = index_by_type(objs)

    out = []
    out.append("MASTER_SPEC (human-readable)")
    out.append("=" * 80)

    if meta:
        out.append("META")
        out.append("-" * 80)
        for k in sorted(meta.keys()):
            if k == "type":
                continue
            out.append(f"{k}: {meta[k]}")
        out.append("")

    out.append("SURFACES")
    out.append("-" * 80)
    for sid in sorted(surfaces.keys()):
        s = surfaces[sid]
        out.append(f"[{sid}]")
        out.append(f"  kind: {s.get('kind','')}")
        out.append(f"  source_file: {s.get('source_file','')}")
        out.append(f"  heading: {s.get('heading','')}")
        out.append(f"  route_ref: {s.get('route_ref','')}")
        req = s.get("requires_capabilities", [])
        out.append(f"  requires_capabilities ({len(req)}):")
        for cid in sorted(req):
            out.append(f"    - {cid}")
        out.append("")

    out.append("ROUTES")
    out.append("-" * 80)
    for rid in sorted(routes.keys()):
        r = routes[rid]
        out.append(f"[{rid}]")
        out.append(f"  surface_id: {r.get('surface_id','')}")
        chain = r.get("provider_chain", [])
        out.append(f"  provider_chain ({len(chain)}):")
        for pid in chain:
            out.append(f"    - {pid}")
        cc = r.get("covers_capabilities", [])
        out.append(f"  covers_capabilities ({len(cc)}):")
        for cid in sorted(cc):
            out.append(f"    - {cid}")
        out.append("")

    out.append("PROVIDERS")
    out.append("-" * 80)
    for pid in sorted(providers.keys()):
        p = providers[pid]
        out.append(f"[{pid}]")
        pc = p.get("provides_capabilities", [])
        out.append(f"  provides_capabilities ({len(pc)}):")
        for cid in sorted(pc):
            out.append(f"    - {cid}")
        out.append("")

    out.append("CAPABILITIES")
    out.append("-" * 80)
    for cid in sorted(caps.keys()):
        c = caps[cid]
        out.append(f"[{cid}]")
        out.append(f"  applies_to: {c.get('applies_to','')}")
        trs = c.get("triggers_rules", [])
        out.append(f"  triggers_rules ({len(trs)}):")
        for rid in sorted(trs):
            out.append(f"    - {rid}")
        out.append("")

    out.append("RULES")
    out.append("-" * 80)
    for rid in sorted(rules.keys()):
        r = rules[rid]
        out.append(f"[{rid}]")
        out.append(f"  rule_layer: {r.get('rule_layer','')}")
        out.append(f"  normativity: {r.get('normativity','')}")
        out.append(f"  scope: {r.get('scope','')}")
        src = fmt_source(r)
        if src:
            out.append(f"  source: {src}")
        hp = r.get("heading_path")
        if hp:
            out.append(f"  heading_path: {hp}")
        stmt = r.get("statement","")
        out.append("  statement:")
        out.append(f"    {stmt}")
        out.append("")

    if impls:
        out.append("IMPLEMENTATIONS")
        out.append("-" * 80)
        for iid in sorted(impls.keys()):
            im = impls[iid]
            out.append(f"[{iid}]")
            out.append(f"  implements_route: {im.get('implements_route','')}")
            pa = im.get("providers_available", [])
            out.append(f"  providers_available ({len(pa)}):")
            for pid in pa:
                out.append(f"    - {pid}")
            dc = im.get("declared_capabilities", [])
            out.append(f"  declared_capabilities ({len(dc)}):")
            for cid in sorted(dc):
                out.append(f"    - {cid}")
            out.append("")

    if others:
        out.append("OTHER OBJECTS")
        out.append("-" * 80)
        out.append(f"count: {len(others)}")
        out.append("")

    path_out.write_text("\n".join(out), encoding="utf-8")

def main(argv):
    if len(argv) not in (2, 3):
        print("Usage: python render_master_spec_txt.py <input.jsonl> [output.txt]")
        return 2
    in_path = Path(argv[1])
    out_path = Path(argv[2]) if len(argv) == 3 else in_path.with_suffix(".txt")
    render(in_path, out_path)
    print(str(out_path))
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
