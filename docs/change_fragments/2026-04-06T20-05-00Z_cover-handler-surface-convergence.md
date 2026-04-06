cover_handler surface convergence

- adds resolver-friendly cover discovery and materialization surfaces based on source refs
- keeps legacy path-based helpers as compatibility wrappers for existing callers
- removes implicit /tmp download fallback from canonical cover materialization flow
- preserves candidate ordering, embedded detection, and deterministic cache semantics
