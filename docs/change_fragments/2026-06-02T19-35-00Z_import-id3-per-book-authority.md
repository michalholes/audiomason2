## Why

Batch imports could write incorrect ID3 tags for non-first books. When the ID3 step was not
explicitly submitted, PHASE 1 persisted default `id3_policy.values` derived from the first
selected book. PHASE 2 then applied those values to every action, which could stamp all output
books with the same title/author.

## What changed

- `plugins/import/phase1_source_intake.py`
  - Build `phase2_inputs.id3_policy.values` from explicit `answers.id3_policy.values` only.
  - Keep per-book authority (`authority_book_meta`) as the default source of metadata tags.
  - Preserve explicit `track_start` in `phase2_inputs.id3_policy` when user provided.

## Result

When the user does not explicitly set global ID3 values, PHASE 2 no longer propagates first-book
metadata across the whole batch. Per-book metadata remains authoritative for each action.
