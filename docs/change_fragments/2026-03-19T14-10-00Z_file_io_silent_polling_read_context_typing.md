2026-03-19T14:10:00Z

File I/O silent polling reads now use a branch-local open_read context flow so
strict static type checking accepts the same explicit opt-in behavior without
changing runtime semantics or low-level observability suppression.
