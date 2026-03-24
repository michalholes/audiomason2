2026-03-24T10:45:00Z

Added specification rules for frontend type authority and strict-readiness.
The spec now requires one compile-time type authority under types/, a compatibility
shim without duplicate truth, no explicit any in authoritative frontend type surfaces,
a dedicated strict typecheck entrypoint before default strict enablement, and real
toolchain typings for Playwright and Node instead of local fake ambient shims.
