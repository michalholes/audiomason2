2026-03-15T23:10:00Z
Fixed the shared Flow JSON local-file picker fallback so returning focus no longer
cancels a valid selection before the change event arrives, and added regression
coverage for both the whole-artifact JSON modal and the per-step JSON modal.
