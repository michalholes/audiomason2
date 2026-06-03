## Why

ID3 tags could still become uniform across a batch even after per-book authority fixes.
In V3, `id3_policy` is written by automatic `data.set` steps from metadata defaults.
Those defaults mirror the first selected book and are not explicit user overrides.

## What changed

- `plugins/import/phase1_source_intake.py`
  - Added `_explicit_id3_values(...)` to keep only ID3 values that differ from current
    metadata defaults.
  - `phase2_inputs.id3_policy.values` now stores only explicit overrides, not implicit
    auto-populated defaults.

## Result

Automatic ID3 defaults no longer override per-book metadata in PHASE 2.
Per-book author/title stay authoritative unless the user provides a real global override.
