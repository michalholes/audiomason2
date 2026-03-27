# Issue 212 v6 - web typing cleanup and v3 test bootstrap

- tightened web interface UI typing so the repo-wide TypeScript check clears without changing tsconfig
- updated import v3 parity and DOM tests to bootstrap the helper script before the main runtime asset
- kept import helper extraction intact while restoring test coverage against the real browser bootstrap shape
