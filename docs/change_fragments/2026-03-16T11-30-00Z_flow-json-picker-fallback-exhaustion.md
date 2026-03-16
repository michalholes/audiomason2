2026-03-16T11:30:00Z
Refined the shared Flow JSON local-file picker fallback so delayed
selections survive post-focus settling, and surfaced explicit UI errors
when the browser closes the dialog without delivering either a
selection or a native cancel event.
