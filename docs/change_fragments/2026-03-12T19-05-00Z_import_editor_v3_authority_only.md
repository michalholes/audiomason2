2026-03-12T19:05:00Z

Import editor authority now repairs active wizard editor state to the default v3 definition, rejects legacy v2 editor writes, keeps the browser and CLI editor surfaces converged on v3 active state, restores v3 runtime compatibility for effective workflow snapshot loading and graph normalization, and refreshes stale pytest and browser assertions for the current prompt-based auto-advance surfaces. Repairs the v3 flow graph typing surface so mypy no longer sees a duplicate local name during graph normalization.
