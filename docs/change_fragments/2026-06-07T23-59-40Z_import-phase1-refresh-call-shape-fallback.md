2026-06-07T23:59:40Z Harden `call.invoke` refresh result shape for running-loop create/resume.

- Added deterministic fallback shaping for `operation_id == import.phase1_refresh`
  from `state.vars` (`phase1` plus author/title/cover loop confirmed maps).
- Successful `call.invoke` refresh calls are now normalized so
  `outputs.result.phase1` is always an object, preventing invariant failures on
  DSL writes like `$.op.outputs.result.phase1`.
- In capture mode, refresh invocation failures now keep the existing error
  envelope but return fallback `result` instead of `None`.
