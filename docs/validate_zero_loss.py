import json, sys
from collections import defaultdict

def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

def main(path):
    objs = load(path)

    meta = objs[0]
    if meta.get("type") != "meta":
        raise SystemExit("FAIL: first object must be meta")

    expected_counts = meta.get("source_files", {})
    actual_counts = defaultdict(int)

    for o in objs[1:]:
        if o.get("type") != "source_line":
            raise SystemExit(f"FAIL: unexpected object type {o.get('type')}")
        sf = o.get("source_file")
        actual_counts[sf.replace("docs/spec/","")] += 1

    for fname, expected in expected_counts.items():
        actual = actual_counts.get(fname, 0)
        if actual != expected:
            raise SystemExit(f"FAIL: file {fname} expected {expected} lines but found {actual}")

    print("ZERO-LOSS VALIDATION OK")
    print(f"Total lines: {meta.get('total_source_lines')}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python validate_zero_loss.py <jsonl>")
        sys.exit(1)
    main(sys.argv[1])