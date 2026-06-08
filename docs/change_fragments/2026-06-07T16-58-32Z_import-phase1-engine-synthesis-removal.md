2026-06-07T16:58:32Z Removed engine-side PHASE 1 synthesis from import session and submit paths.

- Reduced v3 create-time `vars.phase1` seeding to a technical baseline: selection ids/labels,
  authority book mapping, loop-safe defaults, and static policy defaults only.
- Removed submit-time recomputation paths from v3 legacy sync; it now mirrors only
  `inputs`, `selected_author_ids`, and `selected_book_ids` from persisted state.
- Clarified planner authority errors to point directly at missing `vars.phase1` authority paths.
