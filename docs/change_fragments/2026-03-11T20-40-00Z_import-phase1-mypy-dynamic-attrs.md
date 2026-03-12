2026-03-11T20:40:00Z

Replaced direct dynamic attribute writes in the import phase1 runtime
boundary with setattr calls so the wrapper marker and module dispatch
registration remain mypy-compatible.
