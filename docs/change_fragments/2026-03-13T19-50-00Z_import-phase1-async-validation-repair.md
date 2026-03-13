2026-03-13T19:50:00Z
Import PHASE 1 metadata validation now runs safely during session bootstrap and resume under an active event loop, while preserving deterministic fallback authority and runtime projection refresh. The validation helper typing was also tightened so the async repair remains mypy-clean without changing runtime behavior.
