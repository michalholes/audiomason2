2026-06-07T23:59:50Z Import SB-05 parity refresh and confirmed-map determinism.

- Added an explicit v3 `call.invoke` refresh step in
  `plugins/import/dsl/default_wizard_v3_source.json` between
  `resolve_author_ids` and `select_books`.
- The new step (`phase1_refresh_after_author_ids`) calls
  `import.phase1_refresh` in inline capture mode and persists refreshed
  `$.state.vars.phase1` before book selection runs.
- Reworked `ImportPlugin.phase1_refresh` in `plugins/import/plugin.py` to
  rebuild deterministic per-item confirmed maps for author, title, and cover
  loops using loop index, selected ids/paths, and latest loop answers with
  safe fallbacks.
- The refresh output now preserves stable confirmed maps instead of collapsing
  loop authority to the last submitted value.
