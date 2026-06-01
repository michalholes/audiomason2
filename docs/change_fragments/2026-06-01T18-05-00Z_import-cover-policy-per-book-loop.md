# import cover policy per-book loop

- Added a per-book cover decision mode (`per_book`) for PHASE 1 cover policy.
- Introduced deterministic cover selection loop steps (`init_cover_loop`, `cover_mode_item`,
  `cover_mode_item_url`, `store_cover_item`, `cover_loop_check`) via v3 migration so existing
  authored runtime definitions are upgraded safely.
- Added engine sync logic for cover loop confirmations and projection support that maps each
  selected book/source to independent cover decisions (`file`, `embedded`, `skip`, `url`).
- Extended cover projection metadata with per-source allowed modes and per-source discovery hints
  for interactive per-book prompting.
- Fixed v3 runtime `unexpected_token` failure by normalizing cover-loop prompt inputs to avoid
  unsupported nested ExprRef indexing in WizardDefinition nodes.
- Multi-book sessions now default cover mode suggestion to `per_book`, so Enter immediately enters
  per-book cover prompts instead of forcing one global mode choice.
- Fixed per-book `skip`/`file`/`embedded` path crash (`missing_key`) by removing unconditional
  dependency on `cover_mode_item_url` in `store_cover_item` writes and resolving URL only when
  mode is `url`.
