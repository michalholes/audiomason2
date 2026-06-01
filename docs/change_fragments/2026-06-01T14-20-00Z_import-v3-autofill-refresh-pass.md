# import v3 autofill refresh pass after source selection

- Fixed v3 submit flow to refresh PHASE 1 authority immediately after prompt submissions, then run an additional automatic-step pass.
- This allows prompt `autofill_if` conditions that depend on refreshed PHASE 1 selection state to take effect in the same submit cycle.
- Specifically prevents stale `select_books` prompting after selecting a single source item (for example, root-level bundle sources such as `.rar`) when only one book remains.
- Kept deterministic behavior by re-syncing legacy mirrors and rebuilding PHASE 1 authority after the automatic pass.
