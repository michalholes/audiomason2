- import cover and metadata boundaries now resolve Phase 1 callables through the
  registry-owned wizard callable authority instead of boundary-owned provider probing.
- cover and metadata Phase 1 anti-seam tests now enforce registry dispatch and no
  legacy resolve_import_plugin/getattr fallback authority in those boundaries.
- Preserve explicit injected process-runtime cover handler doubles by adapting legacy path-style methods to the published callable contract at the import cover boundary.

- repair: bind legacy callable bridge closures to satisfy ruff B023 and keep mypy-clean repair overlay validation.
