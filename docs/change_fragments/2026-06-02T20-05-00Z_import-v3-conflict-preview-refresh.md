## Why

Some full-flow runs failed at finalize with:

- `INVARIANT_VIOLATION`
- `reason: conflicts_changed`

even when the user only changed values inside the same wizard flow. The preview conflict fingerprint
could become stale after additional PHASE 1 submissions.

## What changed

- `plugins/import/engine_step_submit.py`
  - V3 submit path now refreshes `plan.json` and conflict fingerprint after each accepted submit
    once plan preview exists.
  - This keeps `derived.conflict_fingerprint` aligned with the latest in-flow authority edits
    before `start_processing(confirm=true)` runs the final re-check.

## Result

Finalize conflict re-check remains strict for real post-preview environment changes, while avoiding
false `conflicts_changed` errors caused by stale preview fingerprints during normal in-flow edits.
