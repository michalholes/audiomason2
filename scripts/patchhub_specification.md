# PatchHub Specification (scripts/patchhub)
Status: AUTHORITATIVE SPECIFICATION
Applies to: scripts/patchhub/*
Language: ENGLISH (ASCII ONLY)

Specification Version: 1.1.5-spec
Code Baseline: audiomason2-main.zip (as provided in this chat)

-------------------------------------------------------------------------------

1. Purpose

PatchHub is the web UI for operating the AM Patch runner (scripts/am_patch.py).

PatchHub provides:
- Patch upload and storage under the repo patches directory
- Canonical command parsing and construction for runner invocation
- A single-runner execution queue (one active runner at a time)
- Live observation of runner output and runner jsonl stream
- Browsing of runner artifacts (logs, successful/unsuccessful archives, web job artifacts)
- Limited filesystem operations within a patches-root jail (config gated)

PatchHub does NOT:
- Generate patches
- Modify patch zip contents
- Bypass runner gates
- Replace or re-implement runner logic

All repository mutations are performed only by scripts/am_patch.py.
PatchHub is an operator UI, not the authority.

-------------------------------------------------------------------------------

2. Authority and Constraints

Authority order for PatchHub behavior:
1) AUDIOMASON2_PROJECT_CONTRACT.md (base invariants: determinism, anti-monolith, ASCII)
2) scripts/am_patch.py and its spec/manual (runner is authority)
3) This PatchHub specification
4) PatchHub implementation (scripts/patchhub)

Constraints that apply to scripts/patchhub:
- Deterministic behavior (given same config + same filesystem state + same requests)
- Structural integrity (anti-monolith, no catch-all hubs)
- ASCII-only for authoritative docs and responses using ensure_ascii where applicable
- No hidden network activity

2.1 Versioning and Spec Sync (HARD)

Before changing PatchHub behavior, the developer MUST read this specification.

Any behavior change (UI/API/validation/defaults) MUST include:
- a corresponding update to this specification
- a PatchHub runtime version bump in scripts/patchhub/patchhub.toml ([meta].version)

Versioning uses SemVer: MAJOR.MINOR.PATCH
- MAJOR: incompatible behavior change
- MINOR: backward compatible functionality (additive)
- PATCH: backward compatible bug fix

The runtime version MUST NOT be hardcoded in code.

-------------------------------------------------------------------------------

3. Structure (Modules and Responsibilities)

Primary modules:
- server.py: HTTP routing, request parsing, response writing
- app_core.py: App wiring (composition)
- config.py: TOML config loading (patchhub.toml)
- fs_jail.py: patches-root jail and CRUD gating
- app_api_core.py: config, parse_command, runs, runner_tail, diagnostics
- app_api_jobs.py: jobs enqueue/list/get/log_tail/cancel
- app_api_upload.py: upload patch artifacts
- app_api_fs.py: fs list/read_text/mkdir/rename/delete/unzip
- server_archive.py: /api/fs/archive (selection.zip creation)
- server_events.py: /api/jobs/<job_id>/events (SSE stream from runner jsonl)
- queue.py: job queue, lock, override injection, job persistence
- runner_exec.py: runner subprocess executor
- indexing.py: historical runs indexing from patches/logs
- issue_alloc.py: issue id allocation by scanning patches dirs
- models.py: dataclasses for JobRecord, RunEntry, AppStats

Anti-monolith rule (for PatchHub code):
- No catch-all file names (utils.py/common.py/helpers.py/misc.py forbidden).
- Keep modules responsibility-specific.
- Prefer extraction over growth.

-------------------------------------------------------------------------------

4. Filesystem Model and Jail

4.1 Root of jail
All PatchHub filesystem operations are restricted to patches_root, where:
- patches_root = (repo_root / cfg.paths.patches_root).resolve()

IMPORTANT: PatchHub does NOT provide general repo-root browsing.
It is patches-root only.

4.2 Path input rules (fs_jail.py)
For any rel_path passed to filesystem endpoints:
- MUST be repo-relative to patches_root (no leading "/")
- MUST NOT contain backslashes ("\\")
- MUST be ASCII only
- MUST NOT escape patches_root after resolution
  (candidate = (patches_root / rel_path).resolve(); candidate must be patches_root or under it)

4.3 CRUD gating (fs_jail.py)
CRUD operations are gated by:
- cfg.paths.allow_crud (boolean)
- cfg.paths.crud_allowlist (list of top-level directory names under patches_root)

Allowlist semantics:
- rel_path normalized by stripping leading/trailing "/".
- If normalized is empty, it is allowed only if "" is present in crud_allowlist.
- Otherwise, the top-level segment (before first "/") must be in crud_allowlist.

If allow_crud is false, all mutation endpoints MUST fail with an error.

4.4 Symlink behavior
Jail enforcement uses Path.resolve(). If resolution ends outside patches_root,
the request MUST fail. This rejects symlink escapes that resolve outside the jail.

-------------------------------------------------------------------------------

5. Configuration (patchhub.toml)

5.1 File
Config file: scripts/patchhub/patchhub.toml

5.2 Required keys (hard)
The loader (config.py) requires the following keys to exist:
- [server] host, port
- [runner] command, default_verbosity, queue_enabled, runner_config_toml
- [paths] patches_root, upload_dir, allow_crud, crud_allowlist
- [upload] max_bytes, allowed_extensions, ascii_only_names
- [issue] default_regex, allocation_start, allocation_max
- [indexing] log_filename_regex, stats_windows_days

UI/autofill have defaults (see config.py).

5.3 Key semantics used by API
- cfg.meta.version: shown in UI and /api/config
- cfg.runner.command: runner prefix argv (default ["python3","scripts/am_patch.py"])
- cfg.paths.upload_dir: destination directory for uploads (must be under patches_root)
- cfg.autofill.*: controls /api/patches/latest scanning and filename derivation

-------------------------------------------------------------------------------

6. Response Envelope (JSON)

All JSON responses written by app_support._ok/_err MUST follow:
- Success:
  { "ok": true, ...additional fields... }
- Error:
  { "ok": false, "error": "<string>" }

The following endpoints do NOT use the envelope:
- GET /api/fs/download (raw bytes streaming)
- POST /api/fs/archive (raw zip bytes streaming)
- GET /static/* (raw bytes)

All JSON is encoded with:
- json.dumps(..., ensure_ascii=True, indent=2)
- Content-Type: application/json
- Cache-Control: no-store

6.1 Optional status messages (additive)

JSON responses MAY include an optional field:
- status: ["<string>", ...]

Rules:
- status is additive and MUST NOT break existing clients
- status strings are short, human readable, and non-spammy
- a failure response uses {"ok": false, "error": "..."} and MAY also include status

-------------------------------------------------------------------------------

7. HTTP Surface (Routes, Inputs, Outputs)

All routes are handled in server.py.

7.1 UI routes (GET)
- GET /
  Output: text/html; charset=utf-8 (main UI)

- GET /debug
  Output: text/html; charset=utf-8 (debug UI)

- GET /static/<rel>
  Output: static bytes from scripts/patchhub/static/<rel>
  Rule: static path must not escape static base directory.

7.1.0 UI Layout Notes

In the main UI (templates/index.html), the Start button for launching a run
(HTML id: enqueueBtn) MUST be located in the "B) Start run" section on the
same row as the commit message input (HTML id: commitMsg).

7.1.1 UI Status Bar

The main UI includes a compact status bar for PatchHub events.

HTML element (templates/index.html):
- <div id="uiStatusBar" class="statusbar" aria-live="polite"></div>

Behavior (static/app.js):
- The frontend keeps a ring buffer of recent status lines (default: 20).
- The frontend pushes status lines for:
  - upload (ok/failed)
  - parse_command (ok/failed)
  - enqueue/start job (ok/failed)
  - autofill scan (/api/patches/latest) when the endpoint is called
- If an API response includes status: [...], the frontend appends each line.
- If an API response is {ok:false,error:"..."}, the frontend appends:
  - ERROR: <error>

7.1.2 Live Log Rendering

The main UI includes a live log view for the selected job.

Rendering rule (static/app.js):
- In non-debug live levels, each log line MUST render only ev.msg.
  - If ev.stdout is present, the UI appends a block: STDOUT:\n<text>.
  - If ev.stderr is present, the UI appends a block: STDERR:\n<text>.
- In debug live level, each log line MUST render as:
  <stage> | <kind> | <sev> | <msg>

This is a UI-only rendering rule. The SSE event payload fields
(stage/kind/sev/msg/stdout/stderr) remain unchanged.

7.2 API routes (GET)

7.2.1 GET /api/config
Output schema (success):
{
  "meta": { "version": "<string>" },
  "server": { "host": "<string>", "port": <int> },
  "runner": {
    "command": ["<string>", ...],
    "default_verbosity": "<string>",
    "queue_enabled": <bool>,
    "runner_config_toml": "<string>",
    "success_archive_rel": "<string>"
  },
  "paths": {
    "patches_root": "<string>",
    "upload_dir": "<string>",
    "allow_crud": <bool>,
    "crud_allowlist": ["<string>", ...]
  },
  "upload": {
    "max_bytes": <int>,
    "allowed_extensions": ["<string>", ...],
    "ascii_only_names": <bool>
  },
  "issue": {
    "default_regex": "<string>",
    "allocation_start": <int>,
    "allocation_max": <int>
  },
  "indexing": {
    "log_filename_regex": "<string>",
    "stats_windows_days": [<int>, ...]
  },
  "ui": {
    "base_font_px": <int>,
    "drop_overlay_enabled": <bool>
  },
  "autofill": {
    "enabled": <bool>,
    "poll_interval_seconds": <int>,
    "overwrite_policy": "<string>",
    "fill_patch_path": <bool>,
    "fill_issue_id": <bool>,
    "fill_commit_message": <bool>,
    "scan_dir": "<string>",
    "scan_extensions": ["<string>", ...],
    "scan_ignore_filenames": ["<string>", ...],
    "scan_ignore_prefixes": ["<string>", ...],
    "choose_strategy": "<string>",
    "tiebreaker": "<string>",
    "derive_enabled": <bool>,
    "issue_regex": "<string>",
    "commit_regex": "<string>",
    "commit_replace_underscores": <bool>,
    "commit_replace_dashes": <bool>,
    "commit_collapse_spaces": <bool>,
    "commit_trim": <bool>,
    "commit_ascii_only": <bool>,
    "issue_default_if_no_match": "<string|null>",
    "commit_default_if_no_match": "<string|null>"
  }
}

Notes:
- success_archive_rel is computed by compute_success_archive_rel(repo_root, runner_config_toml, patches_root_rel).
- It reads [paths].success_archive_name from runner_config_toml (default "{repo}-{branch}.zip").
- It resolves branch via: git rev-parse --abbrev-ref HEAD (cwd=repo_root).
  If git fails, or returns "HEAD", it uses runner_config_toml [git].default_branch (fallback "main").
- It substitutes {repo} and {branch}, takes os.path.basename, and ensures a .zip suffix.
- It always returns a relative path string: <patches_root_rel>/<name>.zip.

7.2.2 GET /api/fs/list?path=<string>
Input:
- query param "path" (default empty string)
Output (success):
{
  "ok": true,
  "path": "<string>",
  "items": [
    { "name": "<string>", "is_dir": <bool>, "size": <int>, "mtime": <int> },
    ...
  ]
}
Errors:
- 400 for jail validation errors
- 404 if not a directory

7.2.3 GET /api/fs/read_text?path=<string>&tail_lines=<int>&max_bytes=<int>
Inputs:
- query "path" (required)
- query "tail_lines" (optional; if present and non-empty, tail mode is used)
- query "max_bytes" (optional; default 200000; clamped to [1, 2000000])

Outputs (success):
- Tail mode:
  { "ok": true, "path": "<string>", "text": "<string>", "truncated": false }
- Head mode:
  { "ok": true, "path": "<string>", "text": "<string>", "truncated": <bool> }

Notes:
- Head mode reads full file bytes first, then truncates in memory.
- UTF-8 decode uses errors="replace".

Errors:
- 400 for jail validation errors
- 404 if not a file
- 500 if read_bytes fails

7.2.4 GET /api/fs/download?path=<string>
Output:
- Raw file bytes with guessed Content-Type and Content-Length.
Errors:
- JSON error with 400/404 if jail validation or file not found.

7.2.5 GET /api/patches/latest
Purpose:
- Used by UI autofill/polling to find latest matching file in scan_dir.

Defaulting:
- If scan_dir is empty, it defaults to cfg.paths.patches_root.
- If scan_dir equals patches_root, scan_dir_rel is "".

Behavior:
- If cfg.autofill.enabled is false:
  { "ok": true, "found": false, "disabled": true }
- Only supports:
  choose_strategy == "mtime_ns"
  tiebreaker == "lex_name"
  Otherwise returns error 400.

Scanning rules:
- scan_dir must be under patches_root, else 400.
- Scan is non-recursive; only direct children files.
- Files filtered by scan_extensions, scan_ignore_filenames, scan_ignore_prefixes.
- Best file chosen by max mtime_ns; ties broken by lexicographic name.

Output (found):
{
  "ok": true,
  "found": true,
  "filename": "<string>",
  "stored_rel_path": "<string>",
  "mtime_ns": <int>,
  "token": "<mtime_ns>:<stored_rel_path>",
  "derived_issue": "<string|null>",                 (only if derive_enabled)
  "derived_commit_message": "<string|null>"        (only if derive_enabled)
}

7.2.6 GET /api/runs?issue_id=<int>&result=<string>&limit=<int>
Inputs:
- issue_id (optional): filters to that issue
- result (optional): one of "success"|"fail"|"unknown"|"canceled"
- limit (optional): default 100; clamped to [1, 500]

Data sources:
- logs-based runs from indexing.iter_runs(patches_root, log_filename_regex)
- plus canceled runs derived from PatchHub job.json under artifacts/web_jobs

Sorting:
- runs sorted by (mtime_utc, issue_id) descending
- truncated to limit

Output (success):
{
  "ok": true,
  "runs": [
    {
      "issue_id": <int>,
      "log_rel_path": "<string>",
      "result": "success|fail|unknown|canceled",
      "result_line": "<string|null>",
      "mtime_utc": "<UTC ISO Z string>",
      "archived_patch_rel_path": "<string|null>",
      "diff_bundle_rel_path": "<string|null>",
      "success_zip_rel_path": "<string|null>"
    },
    ...
  ]
}

Derivation details:
- result/result_line parsed from last 200 non-empty lines of log, after ANSI strip.
- archived_patch_rel_path determined by searching latest file in:
  patches/successful or patches/unsuccessful containing "issue_<id>"
- diff_bundle_rel_path determined by searching patches/artifacts for "issue_<id>_diff"
- success_zip_rel_path always set to config-derived success archive rel path.

7.2.7 GET /api/runner/tail?lines=<int>
Input:
- query "lines" (optional; default 200; clamped in read_tail to [1, 5000])

Output (success):
{
  "ok": true,
  "path": "<string>",     (logical path: patches_root/am_patch.log)
  "tail": "<string>"      (last N lines; empty if file missing)
}

Note:
- This tails patches_root/am_patch.log, not a job-local log.

7.2.8 GET /api/jobs
Output:
{
  "ok": true,
  "jobs": [ <JobRecord JSON>, ... ]
}
Jobs are the union of:
- in-memory queue jobs, plus
- on-disk job.json entries (up to 200) not present in memory
Sorted by created_utc descending.

7.2.9 GET /api/jobs/<job_id>
Output:
{ "ok": true, "job": <JobRecord JSON> }
Error 404 if not found in memory or on disk.

7.2.10 GET /api/jobs/<job_id>/log_tail?lines=<int>
Output:
{ "ok": true, "job_id": "<string>", "tail": "<string>" }
Source:
- jobs_root/<job_id>/runner.log (last N lines)
If runner.log missing: tail is empty string.

7.2.11 GET /api/jobs/<job_id>/events
Output:
- text/event-stream; charset=utf-8 (SSE)

Semantics (server_events.py):
- If job not found (neither memory nor disk):
  - returns 200 and immediately emits:
    event: end
    data: {"reason":"job_not_found"}
- Otherwise:
  - Streams "data: <json line>" for each complete line appended to the job jsonl.
  - Emits periodic comment pings every ~10 seconds:
    : ping
  - Ends with:
    event: end
    data: {"reason":"job_completed","status":"<job.status>"}

JSONL source file selection:
- If job exists only on disk:
  - path determined by _job_jsonl_path_from_fields(job_id, mode, issue_id)
- If job in memory:
  - path determined by _job_jsonl_path(job)

JSONL file naming rules:
- finalize_live/finalize_workspace => am_patch_finalize.jsonl
- otherwise issue_id digits => am_patch_issue_<issue_id>.jsonl
- else fallback to am_patch_finalize.jsonl

End-of-stream rule:
- If job status != running and no growth observed for >= 0.5 seconds, stream ends.

7.2.12 GET /api/debug/diagnostics
Output: JSON object (NOT envelope).
Schema (best-effort, current implementation):
{
  "queue": { "queued": <int>, "running": <int> },
  "lock": { "path": "<string>", "held": <bool> },
  "disk": { "total": <int>, "used": <int>, "free": <int> },
  "runs": { "count": <int> },
  "stats": { "all_time": <StatsWindow>, "windows": [<StatsWindow>, ...] }
}
StatsWindow schema:
{ "days": <int>, "total": <int>, "success": <int>, "fail": <int>, "unknown": <int> }

-------------------------------------------------------------------------------

7.3 API routes (POST)

7.3.1 POST /api/parse_command
Input JSON:
{ "raw": "<string>" }

Output (success):
{
  "ok": true,
  "parsed": {
    "mode": "patch|finalize_live|finalize_workspace|rerun_latest",
    "issue_id": "<string>",
    "commit_message": "<string>",
    "patch_path": "<string>"
  },
  "canonical": { "argv": ["<string>", ...] }
}

Parsing rules (command_parse.py):
- shlex.split(raw)
- must contain "scripts/am_patch.py" as an argv element
- supports flags in rest:
  -f => finalize_live (rest must be exactly ["-f"] after filtering)
  -w => finalize_workspace (rest must be exactly ["-w"] after filtering)
  -l => rerun_latest (rest must be exactly ["-l"] after filtering)
- patch mode requires exactly 3 args after scripts/am_patch.py:
  ISSUE_ID (digits), commit message (non-empty), PATCH (non-empty)

Errors:
- 400 with ok=false and error string on parse/validation failure

7.3.2 POST /api/jobs/enqueue
Input JSON fields (minimum accepted by app_api_jobs.py):
- mode: "patch" | "repair" | "finalize_live" | "finalize_workspace" | "rerun_latest"
- issue_id: "<string>"           (optional for patch/repair; auto-allocated if missing)
- commit_message: "<string>"     (required for patch/repair unless raw_command provides)
- patch_path: "<string>"         (required for patch/repair unless raw_command provides)
- raw_command: "<string>"        (optional; if provided, it is parsed and canonicalized)

Behavior:
- If raw_command is present:
  - parse_runner_command(raw_command)
  - canonical argv from parsed command is used
  - missing fields may be filled from body fields as fallback
- If raw_command is absent:
  - finalize/rerun modes ignore issue_id/commit/patch and build canonical from runner_prefix
  - patch/repair requires commit_message and patch_path
  - if issue_id missing, PatchHub auto-allocates it (see Section 11)

Output (success):
{
  "ok": true,
  "job_id": "<string>",
  "job": <JobRecord JSON>
}

JobRecord JSON schema (models.JobRecord):
{
  "job_id": "<string>",
  "created_utc": "<UTC ISO Z string>",
  "mode": "patch|repair|finalize_live|finalize_workspace|rerun_latest",
  "issue_id": "<string>",
  "commit_message": "<string>",
  "patch_path": "<string>",
  "raw_command": "<string>",
  "canonical_command": ["<string>", ...],
  "status": "queued|running|success|fail|canceled|unknown",
  "started_utc": "<UTC ISO Z string|null>",
  "ended_utc": "<UTC ISO Z string|null>",
  "return_code": <int|null>,
  "error": "<string|null>"
}

Notes:
- created_utc/started_utc/ended_utc use format "%Y-%m-%dT%H:%M:%SZ".

7.3.3 POST /api/jobs/<job_id>/cancel
Output (success):
{ "ok": true, "job_id": "<string>" }
Error:
- 409 if cannot cancel (unknown job or job already completed)

7.3.4 POST /api/upload/patch (multipart/form-data)
Input:
- Content-Type must be multipart/form-data
- Must include field "file"

Validation (app_api_upload.py):
- If cfg.upload.ascii_only_names: filename must be ASCII
- size must be <= cfg.upload.max_bytes (else 413)
- extension must be in cfg.upload.allowed_extensions

Storage:
- Stored under cfg.paths.upload_dir, which must be under patches_root.
- Destination filename is os.path.basename(filename).

Output (success):
{
  "ok": true,
  "stored_rel_path": "<string>",
  "bytes": <int>,
  "derived_issue": "<string|null>",             (only if cfg.autofill.derive_enabled)
  "derived_commit_message": "<string|null>"    (only if cfg.autofill.derive_enabled)
}

7.3.5 POST /api/fs/mkdir
Input JSON:
{ "path": "<rel>" }
Output:
{ "ok": true, "path": "<rel>" }

7.3.6 POST /api/fs/rename
Input JSON:
{ "src": "<rel>", "dst": "<rel>" }
Output:
{ "ok": true, "src": "<rel>", "dst": "<rel>" }

7.3.7 POST /api/fs/delete
Input JSON:
{ "path": "<rel>" }
Output:
{ "ok": true, "path": "<rel>", "deleted": <bool> }

7.3.8 POST /api/fs/unzip
Input JSON:
{ "zip_path": "<rel>", "dest_dir": "<rel>" }
Output:
{ "ok": true, "zip_path": "<rel>", "dest_dir": "<rel>" }

IMPORTANT (current implementation limitation):
- Unzip uses ZipFile.extractall(dest) without per-member validation.
- This specification describes the current behavior. It does not claim
  additional zip-slip hardening beyond jail constraints on the destination.

7.3.9 POST /api/fs/archive
Input JSON:
{ "paths": ["<rel>", ...] }

Validation:
- paths must be a non-empty list
- each path normalized: strip whitespace, remove leading "/"
- duplicates removed; ordering is deterministic (sorted unique)

Behavior:
- Collect files for each rel path:
Timestamps:
- Zip entries preserve source file timestamps as written by zipfile.ZipFile.write().
- PatchHub does not normalize timestamps or other per-entry metadata.
- Therefore, archive bytes are stable only if file contents AND file metadata (mtime) are unchanged.

  - File paths are included as-is with arcname equal to rel
  - Directory paths are walked with os.walk:
    - dirnames and filenames sorted
    - each file included with arcname equal to relative path under patches_root
- Build zip bytes "selection.zip" using zipfile.ZIP_DEFLATED

Output:
- Content-Type: application/zip
- Content-Disposition: attachment; filename="selection.zip"
- Body: zip bytes

-------------------------------------------------------------------------------

8. Job Queue, Locking, and Override Injection

8.1 Job IDs
Job IDs are generated by uuid.uuid4().hex (32 lowercase hex characters).

8.2 Persistence
For each job, PatchHub writes:
- jobs_root/<job_id>/job.json
- jobs_root/<job_id>/runner.log (runner stdout/stderr)
Additionally, runner emits a jsonl file into jobs_root/<job_id>/:
- am_patch_issue_<issue_id>.jsonl or am_patch_finalize.jsonl

jobs_root is fixed:
- jobs_root = patches_root/artifacts/web_jobs

8.3 Single-runner rule
Only one runner execution may be active at a time.
Queue worker waits until BOTH are true:
- executor.is_running() is false, AND
- is_lock_held(patches_root/am_patch.lock) is false

8.4 Web override injection (queue._inject_web_overrides)
Before executing a job, PatchHub injects runner overrides into argv
deterministically and idempotently:
- --override json_out=true
- --override patch_layout_json_dir=artifacts/web_jobs/<job_id>

Insertion point:
- immediately after the first argv element that ends with "am_patch.py"
- if not found, append at end

Duplicate suppression:
- if an override key already exists in argv, it is not added again

8.5 Completion status mapping
After runner exits:
- return_code == 0 => job.status = "success"
- return_code != 0 => job.status = "fail"
If job was canceled while running:
- status remains "canceled" and ended_utc is preserved/set.

-------------------------------------------------------------------------------

9. Runner Observation Model (Log + JSONL)

PatchHub provides two complementary streams:
- runner.log (stdout/stderr text) for human reading
- runner jsonl (am_patch_issue_*.jsonl) for structured UI updates

SSE (/api/jobs/<job_id>/events) streams JSONL lines as raw strings in "data:"
frames. PatchHub does not parse or rewrite JSONL lines.

-------------------------------------------------------------------------------

10. Runs Indexing Algorithm (Historical View)

Data source:
- patches_root/logs directory

Log selection:
- files whose filename matches cfg.indexing.log_filename_regex
- issue_id extracted from group(1) of that regex

Result parsing:
- read file as UTF-8 with errors="replace"
- strip ANSI escape sequences
- consider last 200 non-empty lines
- find last line that starts with "RESULT:"
- map:
  "RESULT: SUCCESS" => success
  "RESULT: FAIL" => fail
  otherwise => unknown

Sorting:
- by (mtime_utc, issue_id) descending

-------------------------------------------------------------------------------

11. Issue Allocation (when enqueue patch/repair without issue_id)

When POST /api/jobs/enqueue is called for mode patch/repair and issue_id is empty,
PatchHub allocates issue_id by scanning patches_root for existing issue markers.

Algorithm (issue_alloc.py):
- find_existing_issue_ids scans under:
  - patches_root/logs
  - patches_root/artifacts
  - patches_root/successful
  - patches_root/unsuccessful
  using cfg.issue.default_regex and group(1) as digits
- next id = max(existing)+1 else allocation_start
- clamped to [allocation_start, allocation_max]
- if exceeds allocation_max => error

-------------------------------------------------------------------------------

12. Error Handling and Status Codes

JSON error envelope:
{ "ok": false, "error": "<string>" }

Status codes used:
- 200 success
- 400 validation/jail/config errors
- 404 not found
- 409 conflict (cannot cancel)
- 413 upload too large
- 500 internal errors (e.g., read failure, config invariant violation)

No silent failures:
- On validation/jail failure, PatchHub must not perform partial side effects
  before returning error. (Current code follows this for most endpoints.)

-------------------------------------------------------------------------------

13. Non-Goals

PatchHub is NOT:
- A patch authoring system
- A CI/CD orchestrator
- A replacement for the AM Patch runner
- A general-purpose repository file manager

-------------------------------------------------------------------------------

END OF SPECIFICATION
