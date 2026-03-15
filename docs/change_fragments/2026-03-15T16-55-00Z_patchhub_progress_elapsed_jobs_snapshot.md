2026-03-15T16:55:00Z

PatchHub now retains the last jobs snapshot when progress refreshes omit jobs,
so the Progress header elapsed timer remains visible until jobs are explicitly
cleared. Regression coverage now distinguishes omitted jobs from an explicit
empty jobs list.
