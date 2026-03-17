2026-03-17T18:20:00Z Moved import PROCESS contract execution onto a detached
Core-owned runtime so async caller loops no longer own phase-2 lifetime,
pending canonical jobs can wait non-terminally until runtime startup, later
runtime startup automatically adopts persisted jobs without duplicate
processing, and explicit single-job submit does not sweep unrelated pending
PROCESS jobs from the shared store.
