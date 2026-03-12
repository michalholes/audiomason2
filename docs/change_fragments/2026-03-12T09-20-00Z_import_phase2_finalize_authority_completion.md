- area: import
- type: fix
- summary: |
    Import Phase 2 now preserves authority-driven track_start in job requests.
    Successful finalize writes the report, per-source processing logs, and
    per-book dry-run text artifacts used by rerun surfaces.
    Repair note: processed registry authority normalization now keeps optional
    track_start without breaking static gates.
