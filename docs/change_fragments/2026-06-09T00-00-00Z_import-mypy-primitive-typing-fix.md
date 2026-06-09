2026-06-09T00:00:00Z fixed mypy typing in import primitives without changing runtime behavior.

- Annotated the `io_v1` file-listing path so sorted entries stay typed as `_ListEntry`.
- Replaced the dynamic `getattr(..., "configure", None)` check in `call_v1` with a runtime-checkable protocol guard.
- Kept the plugin configuration and file service behavior unchanged.
