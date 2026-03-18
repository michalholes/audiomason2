2026-03-17T18:50:00Z Moved import PROCESS contract execution onto a detached
Core-owned subprocess authority that keeps canonical jobs persisted in pending
until durable cross-process claim, automatically adopts pending and stranded
running jobs on later authority startup, and preserves single-job submit scope
so CLI and web callers stay thin while phase-2 execution survives caller exit.
Jobs now bind to the session file-service jobs root, child authority inherits both repo and src on PYTHONPATH, and direct orchestration test seams keep local in-process dispatch while helper-driven canonical imports still submit through the detached authority. Canonical import job aliases now refresh stale default-store links so success finalization reads the current session job metadata deterministically.
