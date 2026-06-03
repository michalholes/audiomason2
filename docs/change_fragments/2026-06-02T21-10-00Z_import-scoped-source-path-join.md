## Why

Imports started from a nested source path (for example `inbox/<author-container>`) could fail in
PHASE 2 with `source path missing after staging`. Planned book paths were session-scoped, while
PHASE 2 expected root-relative source paths for file materialization.

## What changed

- `plugins/import/job_requests.py`
  - Added `_root_relative_source_path(...)` and used it when building each action source path.
  - `actions[].source.relative_path` is now rooted against the session source prefix.
  - `source.delete` capability now uses the same rooted source-relative path.
  - Cover candidate matching accepts both scoped and rooted source path variants for compatibility.

## Result

Scoped import sessions no longer fail at PHASE 2 source materialization due to missing source
prefix in action source paths.
