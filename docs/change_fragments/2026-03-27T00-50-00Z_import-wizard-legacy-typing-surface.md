2026-03-27T00:50:00Z

Tightened legacy import wizard typing and aligned the v3 renderer bridge with the authoritative import UI type surface.

Repair note: the issue 212 follow-up keeps session start request typing in the authoritative import UI declaration layer and removes the remaining legacy import wizard TypeScript blockers.

Follow-up repair slices keep the same types/ authority while extending
strict typing across the step modal, JSON modal, and flow canvas helper
surfaces.
