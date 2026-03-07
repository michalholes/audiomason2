# PatchHub Specification (scripts/patchhub)
Status: AUTHORITATIVE SPECIFICATION
Applies to: scripts/patchhub/*
Language: ENGLISH (ASCII ONLY)

Specification Version: 1.9.0-spec
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

2.2 Idle and Background Activity (HARD)

- PatchHub server MUST NOT use timeout-based polling for the main job queue idle loop.
- The job queue idle loop MUST block on queue.get() and MUST wake only on new work or on stop.
- When the PatchHub UI document is hidden (document.hidden == true), the UI MUST pause all periodic refresh timers and MUST close any active SSE/EventSource connections.
- When the document becomes visible again, the UI MUST resume timers and refresh UI state.
- Timer creation MUST be centralized to prevent duplicated timers across multiple hide/show cycles.

2.3 Client Fault Tolerance (HARD)

- PatchHub UI MUST remain functional if any optional client module fails to load
  or throws at runtime ("degraded mode").
- Failures MUST NOT be silently swallowed.
- The UI MUST surface client faults visibly (banner/panel) and MUST also log them
  via console.error.
- A "degraded mode" indicator MUST be shown whenever a client module is missing
  or failed.
- A fault-tolerance bootstrap script MUST be loaded before any other UI scripts
  and MUST:
  - register window "error" and "unhandledrejection" handlers,
  - provide a safe accessor for optional modules (missing module => visible
    fault + fallback no-op behavior),
  - keep a bounded in-memory list of recent client faults for display.

2.3.1 Bootstrap Identity and No-Go Policy (HARD)

- The PatchHub client bootstrap script MUST be exactly:
  - scripts/patchhub/static/patchhub_bootstrap.js

- index.html MUST load the bootstrap script before any other client script.
- index.html MUST NOT load any other PatchHub client scripts directly.
  - In particular, app.js MUST NOT be included via a direct <script src=...>.

- The bootstrap script is NO-GO.
  - Any patch touching scripts/patchhub/static/patchhub_bootstrap.js MUST be
    rejected unless the issue text contains an explicit approval line from
    Michal permitting a bootstrap change.

2.3.2 Debug Survivability and Fatal Degraded Flag (HARD)

- GET /debug MUST remain functional even if the main UI fails to load or throws
  at runtime.
- The bootstrap MUST persist a bounded client status log to localStorage key:
  - patchhub.client_status_log
- The /debug UI MUST display patchhub.client_status_log.

- The bootstrap MUST set a "degraded" flag in patchhub.client_status_log on the
  first fatal start failure.
- A fatal start failure includes at minimum:
  - failure to load runtime script(s),
  - failure to load app.js,
  - app init throwing (after app.js was loaded).

2.4 Refresh Policy: ACTIVE vs IDLE (HARD)

- The UI MUST implement two refresh modes:
  - ACTIVE: while a patching job is running (or an active job is selected), the
    UI MUST provide near-realtime updates for:
    - live logs,
    - job state/progress (top-right),
    - stop/cancel responsiveness.
  - IDLE: when no patching is active, the UI MUST use a deterministic
    backoff policy for visible-tab refresh (see 2.5.1). The UI MUST NOT
    refresh more frequently than the first backoff interval.
- In IDLE mode, the UI MUST NOT re-fetch or re-render data that has not changed
  ("conditional refresh").
- Timer creation MUST remain centralized and MUST NOT duplicate refresh loops.

2.5 Conditional Refresh Tokens (HARD)

- APIs that return frequently refreshed UI data MUST expose a stable "version
  token" for each logical payload, including at minimum:
  - runs list,
  - jobs list,
  - header/status summary,
  - latest patch discovery.
- The UI MUST supply the last-seen token on refresh.
- If the token matches (no changes), the server MUST return an "unchanged"
  response without recomputing expensive payloads.
- The UI MUST skip DOM updates if the data is unchanged.


2.5.1 Deterministic IDLE Visible Backoff (HARD)

Scope
- Applies only when the UI is in IDLE mode and document.hidden == false.
- ACTIVE mode behavior MUST NOT be changed by this policy.

Backoff sequence
- The UI MUST use a fixed, deterministic sequence of refresh intervals
  (no jitter). Default sequence: 2s, 5s, 15s, 30s, 60s.
- The sequence MUST be controlled by a single JS constant to enable rollback
  by editing one value.

Reset and advance rules
- The UI MUST track last-seen change tokens (sig) for: jobs, runs, header, latest patch discovery.
- On a refresh attempt, if all sig values are unchanged, the UI MUST advance
  one step in the backoff sequence (capped at the last element).
- If any sig value changes, the UI MUST reset to the first element.
- The UI MUST NOT update the DOM when the server indicates unchanged=true.

Failure mode
- If a sig is incorrect (false-unchanged), UI updates will be delayed.
- Therefore, sig MUST cover all user-visible state for that payload, including
  memory-resident queue jobs and on-disk job.json files.

Server contract (canonical transport: HTTP ETag/304)
- Each refresh API MUST compute a stable string token field: sig.
- The server MUST expose the current token as an HTTP ETag header.
- The UI MUST send the last-seen token using If-None-Match.
- If If-None-Match matches the current token, the server MUST respond with:
  HTTP 304 Not Modified (no response body) and MUST NOT compute expensive payload fields.

JSON fallback (compatibility)
- Each refresh API MUST also accept the last-seen token via query parameter since_sig.
- If since_sig matches current sig, the server MUST respond with:
  { ok: true, unchanged: true, sig: <sig> }
  and MUST NOT compute expensive payload fields.
2.6 Runs Indexing: Tail Scan and Cache (HARD)

- Runs result parsing MUST scan from end-of-file and MUST stop as soon as RESULT
  is found.
- Unchanged logs MUST NOT be re-read. Caching MUST be keyed by deterministic file
  metadata (e.g. mtime_ns and size).
- The runs list MUST be able to scale to thousands of logs without full file
  reads on each refresh.

2.6.1 Background Indexer for jobs/runs/ui_snapshot (HARD)

Normal path behavior
- When a background indexer is ready, list endpoints MUST NOT perform any
  filesystem scan or parsing work in the request handler path.
  - This includes scanning logs, scanning web job artifacts, reading job.json,
    and reading/parsing run logs.
- In this state, list endpoints MUST serve precomputed, in-memory snapshots and
  MUST limit request handler work to O(n) filtering + JSON serialization.

Indexer behavior
- PatchHub MUST run a background indexer task that maintains snapshots for:
  - jobs list (see 7.2.8)
  - runs list (see 7.2.6 runs; includes canceled runs)
  - ui_snapshot payload (see 2.9)
- On server startup, the indexer MUST perform an initial full scan/build for
  those snapshots.
- After startup, the indexer MUST refresh snapshots on a deterministic polling
  interval configured by cfg.indexing.poll_interval_seconds.
- The refresh work MUST execute outside request handlers.

Failure mode
- A bug or crash in the indexer can cause stale UI data.
- If the indexer is not ready, or if it is in an error state, endpoints MAY
  fall back to legacy on-demand disk scanning behavior.
  - This is the only permitted case where request handlers may scan or parse
    disk state for jobs/runs/ui_snapshot.

Debug support
- PatchHub MUST provide a debug-only endpoint to trigger a full rescan:
  POST /api/debug/indexer/force_rescan (see 7.3.10).

2.7 Live Events Rendering Limits (HARD)

- The UI MUST throttle high-frequency live event rendering and MUST bound
  in-memory live event storage (ring buffer).
- Throttling MUST NOT break stop/cancel responsiveness.



2.8 Single-Flight Requests (HARD)

Goal: prevent overlapping requests that create backend pressure when responses are slow.

- For each refresh endpoint (jobs, runs, header/stats, ui_snapshot, latest patch),
  the UI MUST enforce single-flight: at most one in-flight request per endpoint.
- If a periodic tick occurs while a request for that endpoint is still in-flight,
  the UI MUST NOT start a second request for the same endpoint.
- If a user action triggers a refresh while a request is in-flight, the UI MUST
  abort the prior request and start a new request.
- Aborting MUST use AbortController.
- The behavior MUST be deterministic (no jitter).

2.9 Batching: /api/ui_snapshot (HARD)

Goal: reduce HTTP overhead by batching multiple list endpoints into one response.

Endpoint
- GET /api/ui_snapshot

Payload
- The response MUST include, at minimum:
  - jobs list (thin, see 2.11),
  - runs list (thin, see 2.11),
  - workspaces list (thin, see 2.11),
  - header/status summary (diagnostics/stats payload used by the header).

Tokens and caching
- The server MUST compute and expose a stable sig for each sub-payload:
  - jobs_sig, runs_sig, workspaces_sig, header_sig.
- The server MUST compute a snapshot_sig that changes if any sub-payload changes.
- The response MUST include:
  { ok: true, snapshot: { jobs: [...], runs: [...], workspaces: [...], header: {...} },
    sigs: { jobs: <jobs_sig>, runs: <runs_sig>, workspaces: <workspaces_sig>,
      header: <header_sig>, snapshot: <snapshot_sig> } }
- The snapshot endpoint MUST support ETag/304 using snapshot_sig.

Client behavior
- In IDLE mode, the UI SHOULD prefer /api/ui_snapshot over multiple list calls.
- ACTIVE mode MAY continue to use specialized endpoints for near-realtime
  (tail, live stream) without routing through the snapshot endpoint.

2.10 HTTP ETag and 304 Not Modified (HARD)

- For refresh APIs covered by 2.5 / 2.5.1, ETag/304 is the canonical transport.
- The ETag value MUST be derived from the current sig.
- The server MUST treat If-None-Match strictly:
  - exact string match => 304 with empty body.
- The server MUST include the ETag header on 200 responses.
- The server MAY include the ETag header on 304 responses.

2.11 Thin DTO Contracts (HARD)

Jobs list item (JobListItem)
- jobs list endpoints MUST return a thin DTO with fields:
  - job_id: string
  - status: string
  - created_utc: string
  - started_utc: string|null
  - ended_utc: string|null
  - mode: string
  - issue_id: string
  - commit_summary: string (single line; deterministic truncation)
  - patch_basename: string|null (filename only; no directory; null if absent)

Runs list item (RunListItem)
- runs list endpoints MUST return a thin DTO with fields:
  - issue_id: int
  - result: string
  - mtime_utc: string
  - log_rel_path: string
  - artifact_refs: array of string (may be empty)

Workspaces list item (WorkspaceListItem)
- workspace list endpoints MUST return a thin DTO with fields:
  - issue_id: int
  - workspace_rel_path: string
  - state: string (DIRTY|CLEAN|KEPT_AFTER_SUCCESS)
  - busy: bool
  - mtime_utc: string
  - attempt: int|null
  - commit_summary: string|null (single line; deterministic truncation)
  - allowed_union_count: int|null

Detail separation
- List DTOs MUST NOT include full commit message text, raw command text, or
  patch filesystem paths.
- Detailed job/run fields MUST be served only by detail endpoints.
- For runs, PatchHub does not define a separate run-detail JSON route beyond
  GET /api/runs?issue_id=<int> (optionally with limit=1); log text MUST be fetched
  via GET /api/fs/read_text using the run's log_rel_path (tail_lines recommended).

2.12 Server Sorting and Filtering Cost (HARD)

- List endpoints MUST avoid repeated full materialization + full sort work when
  there is no change.
- For default (unfiltered) list views, the unchanged path MUST return 304 (or
  JSON unchanged) without constructing the list or sorting it.
- If server-side sort/filter is expensive, the implementation MUST use
  incremental or cached ordering keyed by deterministic signatures.


-------------------------------------------------------------------------------

3. Structure (Modules and Responsibilities)

Primary modules:
- asgi/asgi_app.py: HTTP routing, request parsing, response writing (ASGI backend)
- asgi/async_app_core.py: App wiring (composition) for ASGI backend
- config.py: TOML config loading (patchhub.toml)
- fs_jail.py: patches-root jail and CRUD gating
- app_api_core.py: config, parse_command, runs, runner_tail, diagnostics
- app_api_jobs.py: jobs enqueue/list/get/log_tail/cancel
- app_api_upload.py: upload patch artifacts
- app_api_fs.py: fs list/read_text/mkdir/rename/delete/unzip
- asgi/asgi_app.py: /api/fs/archive and /api/jobs/<job_id>/events routes
- asgi/async_event_pump.py: single socket->jsonl event persistence pump (one per job)
- asgi/job_event_broker.py: in-memory per-job event broadcast used for low-latency SSE
- asgi/sse_jsonl_stream.py: JSONL tailing fallback for SSE after restart
- asgi/async_queue.py: job queue, lock, override injection, job persistence
- asgi/async_runner_exec.py: runner subprocess executor
- indexing.py: historical runs indexing from patches/logs
  - Uses deterministic in-process caching for /api/runs results.
  - Cache invalidation is signature-based: (count, max mtime_ns) of matching log files.
- job_store.py: on-disk job.json reader and job listing
  - Uses deterministic in-process caching for /api/jobs/list disk scans.
  - Cache invalidation is signature-based: (count, max mtime_ns) of job.json files.
- issue_alloc.py: issue id allocation by scanning patches dirs
- models.py: dataclasses for JobRecord, RunEntry, AppStats

Anti-monolith rule (for PatchHub code):
- No catch-all file names (utils.py/common.py/helpers.py/misc.py forbidden).
- Keep modules responsibility-specific.
- Prefer extraction over growth.

-------------------------------------------------------------------------------


3.1 UI Fault Containment and Degraded Mode (HARD)

Goal: A failure of any optional UI module MUST NOT crash the PatchHub UI shell.
The UI MUST remain operable in a degraded mode.

Definitions:
- Shell: the always-loaded bootstrap layer responsible for initialization, routing UI events, and rendering fallbacks.
- Module: an optional feature bundle that registers capabilities with the Shell (e.g. live log view, progress rendering).

3.1.1 Shell requirement (HARD)
- A Shell layer MUST exist and MUST be the only mandatory bootstrap.
- The Shell MUST be able to start and render "minimal viable UI" even when zero modules are loaded.

3.1.2 Dispatcher / capability mediator (HARD)
- All calls from the Shell/application code to module functionality MUST go through a centralized dispatcher (capability mediator).
- The dispatcher MUST provide at least:
  - has(capability_name) -> bool
  - call(capability_name, *args, **kwargs) -> any
- call(...) MUST be existence-safe:
  - Calling a non-existent capability MUST NOT raise an exception.
  - It MUST return a stable default (implementation-defined; MUST be documented).
- call(...) MUST be exception-safe:
  - Exceptions thrown by a capability handler MUST be caught inside the dispatcher.
  - The exception MUST NOT propagate to the top-level UI runtime.
- The dispatcher MUST be fault-aware:
  - When a capability throws, its owning module MUST be marked faulted and further calls MAY be short-circuited to defaults.

3.1.3 Deterministic module registration (HARD)
- Each module MUST register itself with:
  - a stable module name (ASCII),
  - a deterministic list of exported capabilities,
  - an optional version string.
- The Shell MUST maintain a module registry with states at minimum:
  - missing, ready, faulted
  - and last_error (string) for diagnostics.

3.1.4 Robust module loading (HARD)
- Module loading MUST provide an explicit success/failure signal to the Shell.
- A module load failure (e.g. 404, parse error) MUST NOT crash the UI.
- The Shell MUST mark the module as missing and render fallbacks for dependent sections.

3.1.5 Explicit UI fallbacks (HARD)
- Any UI section that depends on an optional capability MUST have an explicit fallback renderer.
- Fallback UI MUST clearly indicate degraded mode and identify the missing/faulted module/capability.

3.1.6 Timer/event crash-chain prevention (HARD)
- Top-level periodic refresh ticks and event entrypoints MUST be guarded so that one exception does not stop the loop.
- Any module-invoking work inside timers/events MUST use the dispatcher.

3.1.7 Minimal viable UI without modules (HARD)
Minimal viable UI MUST work when all modules are missing/faulted:
- Patch upload (UI and API path unchanged).
- Start run (enqueue) (UI and API path unchanged).
- Manual refresh of runs/jobs/fs (at least raw JSON rendering is acceptable).
- Display of error status and degraded-mode state.

3.1.8 UI module contract (HARD)
The specification MUST treat modules as optional and MUST define:
- registration shape (module name, capability map),
- dispatcher semantics (existence-safe + exception-safe + fault-aware),
- module registry states and diagnostics fields,
- required fallback behavior for missing/faulted capabilities.


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
- If normalized contains no "/", it is a root-level entry (file or directory).
  It is allowed if "" is present in crud_allowlist, or if the exact name is present.
- Otherwise, the top-level segment (before first "/") must be in crud_allowlist.
- For the Workspace inventory feature, PatchHub CRUD MAY be enabled for workspace
  trees by including "workspaces" in crud_allowlist.
- When "workspaces" is present in crud_allowlist, the existing filesystem mutation
  endpoints remain authoritative for workspace delete/rename/mkdir/unzip behavior.

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

5.2.1 Optional keys (server)

- [server] backend (string)
  - "asgi": async backend (FastAPI + uvicorn). This is the only supported backend.
  - "sync": removed / unsupported (legacy synchronous backend)

Default behavior is backend="asgi".

5.2.2 Optional keys (indexing)

- [indexing] poll_interval_seconds (int, default 2)
  - Polling interval for the background indexer described in 2.6.1.

5.3 Key semantics used by API
- cfg.meta.version: shown in UI and /api/config
- cfg.runner.command: runner prefix argv (default ["python3","scripts/am_patch.py"])
- cfg.paths.upload_dir: destination directory for uploads (must be under patches_root)
- cfg.autofill.*: controls /api/patches/latest scanning and filename derivation

UI behavior toggles (additive):
- cfg.ui.clear_output_on_autofill (bool, default true)
  If true, when the UI detects a new autofill token it clears the previous output
  (live log, tail view, progress summary and steps) and suppresses idle tail refresh.
- cfg.ui.show_autofill_clear_status (bool, default true)
  If true and output is cleared due to autofill, the UI sets the status bar line:
  "autofill: loaded new patch, output cleared".
- cfg.ui.idle_auto_select_last_job (bool, default false)
  If true, when idle and no job is selected, the UI auto-selects the most recent job.

Autofill zip filtering (additive):
- cfg.autofill.scan_zip_require_patch (bool, default false)
  If true, /api/patches/latest ignores .zip candidates that do not contain at least one
  file entry ending with ".patch" anywhere in the zip.

Autofill issue id from zip (additive):
- cfg.autofill.zip_issue_enabled (bool, default true)
  If true, PatchHub reads an issue id from a root-only text member in a selected/uploaded
  .zip and uses it as the derived issue id.
- cfg.autofill.zip_issue_filename (string, default "ISSUE_NUMBER.txt")
  Zip member name to read. The member MUST be at the zip root (no "/" or "\").
- cfg.autofill.zip_issue_max_bytes (int, default 128)
  Maximum uncompressed size allowed for the issue file.
- cfg.autofill.zip_issue_max_ratio (int, default 200)
  Compression ratio guard (file_size/compress_size).

Validation rules:
- Content MUST be ASCII-only and MUST NOT contain "\r".
- PatchHub strips at most one trailing "\n"; other whitespace is preserved.
- Result MUST be digits only (str.isdigit()).

Derivation precedence:
1) Valid issue id from zip ISSUE_NUMBER.txt
2) Filename derivation via cfg.autofill.issue_regex
3) cfg.autofill.issue_default_if_no_match

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

Result badge sizing rule (UI):
- The result badge text (progress summary) MUST be approximately 2x the step header size,
  and MUST NOT dominate the right pane.

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

7.1.3 Progress Card Rendering (Variant 2)

The main UI includes a Progress card (right sidebar) that renders per-step status
using runner textual markers found in the active log tail.

HTML elements (templates/index.html):
- <div id="progressSteps" class="progress-steps"></div>
- <div id="progressSummary" class="progress-summary muted"></div>

Parsing source (static/app.js):
- The UI consumes the live log tail text (same source used for the Tail view).
- Step transitions are derived from lines that begin with:
  - DO: <STEP>
  - OK: <STEP>
  - FAIL: <STEP> (preferred for explicit step failure)
  - ERROR: ... or generic FAIL ... (fallback: marks the last running step as failed)

Rendering rules:
- Each discovered step is rendered in first-seen order.
- Per-step states:
  - pending: gray dot
  - running: yellow dot and a RUNNING pill
  - ok: green dot
  - fail: red dot
- Exactly one step is shown as running (the most recent DO without a later OK/FAIL).

Summary rule:
- progressSummary shows the most recent RESULT:/STATUS:/FAIL:/OK:/DO: line
  (compact single-line status for quick scanning).

This is a UI-only rendering rule. Runner output format is unchanged.

7.1.4 Preview Default Visibility (HARD)

The Preview panel is collapsed by default.
The UI MUST NOT auto-expand the Preview panel after:
- Parse (parse_command)
- Enqueue/Start run

Preview visibility is controlled only by explicit user interaction
(Preview buttons).

7.1.5 Quick Actions Removal

The "Quick actions" card is not present in the main UI.
Filesystem navigation remains available via the Files panel.

7.1.6 Main UI Layout Ordering

The main UI layout is deterministic and layout-only. This section changes card
placement only; it does not change queue behavior, validation rules, or API
semantics.

Header rules (templates/index.html):
- The header MUST render only the top title/status row.
- The header MUST NOT render parseHint or enqueueHint.
- enqueueHint MUST render inside the Start run card.
- parseHint MUST render inside the Advanced card.

Left sidebar order (top to bottom):
- Active job
- Workspaces
- Stats
- Runs

Right sidebar order (top to bottom):
- Progress
- Jobs
- Preview
- Advanced

Advanced card requirements:
- The UI MUST provide a dedicated "Advanced" card in the right
  sidebar.
- The card MUST contain the canonical runner command controls:
  - rawCommand
  - parseBtn
  - previewToggle
  - parseHint
- The Advanced card MUST render below the Preview card.

This is a layout-only requirement. Existing element ids and existing client
behavior remain unchanged.

7.1.4 Sidebar Collapsible Lists (Runs, Jobs)

The main UI includes three sidebar lists that are operator convenience only:
- Workspaces list (left sidebar; above Stats and Runs)
- Runs list (left sidebar)
- Jobs list (right sidebar)

These lists MUST be collapsible and MUST be hidden by default.

HTML elements (templates/index.html):
- Workspaces:
  - toggle button: <button id="workspacesCollapse" ...>
  - wrapper: <div id="workspacesWrap" class="hidden"> ... </div>
- Runs:
  - toggle button: <button id="runsCollapse" ...>
  - wrapper: <div id="runsWrap" class="hidden"> ... </div>
- Jobs:
  - toggle button: <button id="jobsCollapse" ...>
  - wrapper: <div id="jobsWrap" class="hidden"> ... </div>

Behavior (static/app.js):
- Default visibility:
  - workspacesVisible = false
  - runsVisible = false
  - jobsVisible = false
- UI state persistence uses localStorage keys:
  - amp.ui.workspacesVisible ("1" or "0")
  - amp.ui.runsVisible ("1" or "0")
  - amp.ui.jobsVisible ("1" or "0")
- If a key is missing or invalid, the default is hidden ("0").

Button text:
- When the wrapper is hidden, the corresponding button MUST display: Show
- When the wrapper is visible, the corresponding button MUST display: Hide

Workspace list item content (UI)

The Workspaces list is an operator convenience view.
Each list item MUST provide a meaningful summary without requiring a click.

Required visible fields per item:
- issue id (rendered as "#<id>")
- state badge (DIRTY, CLEAN, or KEPT_AFTER_SUCCESS)
- commit message summary when available
- attempt when available
- allowed_union_count when available
- busy marker when the same issue currently has a queued/running job
- actions: Open, Finalize (-w), Delete

Layout requirements:
- First line MUST show: issue id and state badge.
- Commit summary MUST be on its own line when present.
- Meta line MUST include: attempt, allowed_union_count, busy marker, and last
  activity time when present.
- Actions MUST operate as follows:
  - Open: navigate the Files panel to workspace_rel_path.
  - Finalize (-w): enqueue a standard finalize_workspace job via the existing
    jobs enqueue API; PatchHub MUST NOT bypass the queue.
  - Delete: use the existing filesystem delete endpoint against workspace_rel_path.

Terminology rule:
- The UI label for this card MUST be "Workspaces".
- The UI MUST NOT label the card as "In-progress workspaces" or equivalent,
  because a workspace directory may exist after a successful run.

This is a UI/API behavior change. The queue model and runner authority are unchanged.

Jobs list item content (UI)

The Jobs list is an operator convenience view.
Each list item MUST provide a meaningful summary without requiring a click.

Required visible fields per item:
- issue id (rendered as "#<id>"; if missing, render "(no issue)")
- status (uppercase)
- commit message summary (single line; deterministic truncation)
- mode
- patch basename (filename only)
- duration in seconds when both started_utc and ended_utc are available

Layout requirements:
- First line MUST show: issue id and status.
- Commit summary MUST be on its own line.
- Meta line MUST include: mode, patch basename (when present), and duration (when present).

Forbidden in visible item text:
- job_id (may exist only as an internal data attribute for selection)

7.1.6 Autofill Token Change Output Clearing (UI)

When autofill is enabled and the UI detects that /api/patches/latest returns a new
token value, the UI may clear output from the previous patch run.

Config gates (patchhub.toml [ui]):
- clear_output_on_autofill (default true)
  If true, on new token detection the UI clears:
  - the live log view (SSE rendered events),
  - the Tail view,
  - the Progress summary and step list.

  The UI also suppresses idle tail refresh so that the cleared output does not
  immediately reappear from periodic /api/runner/tail polling.

- show_autofill_clear_status (default true)
  If true and output is cleared due to autofill, the UI status bar is set to the
  exact line: "autofill: loaded new patch, output cleared".

Job selection interaction:
- Manual job selection (click on an item in the Jobs list) re-enables output
  refresh and shows that job output.
- Starting a new job (enqueue success) re-enables output refresh for that job.

Idle auto-select:
- If idle_auto_select_last_job is false (default), the UI does not auto-select
  the most recent job when idle.
- If idle_auto_select_last_job is true, the UI preserves the legacy behavior
  and auto-selects the most recent job when idle.

Running job exception:
- If a job is running and no job is selected, the UI selects the running job.

7.1.7 Missing patchPath Clears Run Fields (UI) (HARD)

Rule:
- The UI MUST enforce the following invariant:
- If the file referenced by the current Run patchPath does not exist on disk,
  the UI MUST set:
  - issueId = ""
  - commitMsg = ""
  - patchPath = ""

Notes:
- This clearing is unconditional with respect to user edits, autofill, dirty flags,
  and overwrite policies.

7.1.8 Mode Reset After Terminal Job (UI) (HARD)

Rule:
- After any job reaches a terminal state (success, failed, canceled),
  the UI MUST set the mode dropdown to: patch.

Additionally, after resetting mode to patch due to a terminal job state,
  the UI MUST clear the start-form inputs: issueId, commitMsg, patchPath, rawCommand.


Notes:
- This rule applies to all UI-exposed modes (patch, finalize_live, finalize_workspace, rerun_latest).
- repair is a legacy mode supported only for backward compatibility via API/parse; UI MUST NOT expose repair in the mode dropdown.

7.1.9 Autofill New Patch Token Forces Patch Mode (UI) (HARD)

Rule:
- When /api/patches/latest returns a new token (a different patch than previously
  seen), the UI MUST:
  - set mode dropdown to: patch
  - set issueId, commitMsg, patchPath from the new autofill payload
  - clear rawCommand (if present)


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
    "stats_windows_days": [<int>, ...],
    "poll_interval_seconds": <int>
  },
  "ui": {
    "base_font_px": <int>,
    "drop_overlay_enabled": <bool>,
    "clear_output_on_autofill": <bool>,
    "show_autofill_clear_status": <bool>,
    "idle_auto_select_last_job": <bool>
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

7.2.2 GET /api/fs/stat?path=<string>
Input:
- query parameter: path (string, relative to patches jail)
Output:
{ "ok": true, "path": "<string>", "exists": <bool> }
Semantics:
- exists is true iff the referenced file exists on disk within jail constraints.
- For path == "", the endpoint MUST return exists == true.

7.2.3 GET /api/fs/list?path=<string>
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

7.2.4 GET /api/fs/read_text?path=<string>&tail_lines=<int>&max_bytes=<int>
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

7.2.5 GET /api/fs/download?path=<string>
Output:
- Raw file bytes with guessed Content-Type and Content-Length.
Errors:
- JSON error with 400/404 if jail validation or file not found.

7.2.5a GET /api/workspaces
Output schema (success):
{
  "ok": true,
  "items": [<WorkspaceListItem>, ...],
  "sig": "<string>"
}

Rules:
- The endpoint MUST derive workspace paths from runner config state, not from a
  hardcoded patches/workspaces path.
- The endpoint MUST expose workspace_rel_path relative to patches_root.
- The endpoint MUST classify state deterministically:
  - DIRTY: the workspace repository has tracked or untracked changes.
  - CLEAN: the workspace exists and the workspace repository is clean.
  - KEPT_AFTER_SUCCESS: the workspace exists and the latest known run result for
    the same issue is success.
- The endpoint MUST set busy=true when the same issue currently has a queued or
  running job in PatchHub.
- The endpoint MUST support ETag/304 using sig.

7.2.6 GET /api/patches/latest
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
- If cfg.autofill.scan_zip_require_patch is true:
  - .zip candidates are considered only if the zip contains at least one file entry
    ending with ".patch" (case-insensitive), anywhere in the zip.
  - corrupted/unreadable zips are ignored (no 500); they count as ignored_zip_no_patch.
- Best file chosen by max mtime_ns; ties broken by lexicographic name.

Status counters (additive):
- ignored_zip_no_patch=<int>
  Count of ignored .zip candidates due to missing any .patch file entry, including
  corrupted/unreadable zips.

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
"mtime_utc": "<UTC ISO Z string>",
"artifact_refs": ["<string>", ...]
    },
    ...
  ]
}

Derivation details:
- result parsed from last 200 non-empty lines of log, after ANSI strip.
- artifact_refs is a list of existing artifact rel paths under patches_root for the issue_id:
  - archived patch: latest file in patches/successful or patches/unsuccessful containing "issue_<id>"
  - diff bundle: latest file in patches/artifacts containing "issue_<id>_diff"
  - success zip: config-derived success archive rel path when present
- missing artifacts are omitted (artifact_refs may be empty).

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
  "jobs": [ <JobListItem JSON>, ... ]
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

Semantics (asgi/asgi_app.py):
- If job not found (neither memory nor disk):
  - returns 200 and immediately emits:
    event: end
    data: {"reason":"job_not_found"}
- Otherwise:
- On enqueue (job created and queued), the server MUST ensure the job JSONL exists
  and contains at least one "queued/accepted" event line, so that clients see
  immediate output without waiting for the job to enter "running".
- While job status is "queued" (or "running"), the server MUST NOT emit an "end"
  event solely because the JSONL file does not yet exist.
  - Streams "data: <json line>" for each complete line appended to the job jsonl.
  - On connection, the server SHOULD replay a recent tail of persisted JSONL events
    (default: last 500 lines) before switching to broker live streaming.
  - Live events SHOULD appear in the UI with low latency (no polling batching).

Runner IPC event persistence robustness (HARD):
- The job event pump MUST NOT rely on asyncio StreamReader.readline() limits.
- The pump MUST read the IPC stream in chunks and split on "\n".
- The pump MUST persist each complete JSONL line as-is (after UTF-8 decode).
- This raw capture rule includes IPC control and reply frames received on the
  job socket.
- If a single line grows beyond 64 MiB without a newline, the pump MUST drop
  the partial buffer and emit a JSON notice line with:
  {"type":"patchhub_notice","code":"IPC_LINE_TOO_LARGE_DROPPED",...}.
  - Emits periodic comment pings every ~10 seconds:
    : ping
  - Ends with:
    event: end
    data: {"reason":"job_completed","status":"<job.status>"}

Lifecycle invariants (HARD):
- The server MUST treat tail-based streaming and broker-based streaming as
  equivalent with respect to termination semantics.
- Completion ordering MUST be:
  1) Set final job status (success|fail|canceled)
  2) Persist final job state to disk
  3) Close the live broker (if any)
  4) Emit SSE end trailer:
     event: end
     data: {"reason":"job_completed","status":"<job.status>"}
  The status carried in the end trailer MUST be the final persisted status.
- Silent termination (stream ends without an explicit "event: end") is forbidden.
- Broker close MUST be deterministic:
  - Backpressure MAY drop data lines,
  - but MUST NOT drop the broker termination signal (subscriber loops MUST end).
- After successful enqueue (HTTP 200 for POST /api/jobs/enqueue),
  GET /api/jobs/<job_id>/events MUST NOT return {"reason":"job_not_found"}

SSE source rule (HARD):
- SSE MUST NOT connect to the runner IPC socket directly.
- Live SSE streaming MUST use an in-memory job event broker fed by the job event pump.
- JSONL tailing is permitted only as a fallback for historical jobs or after restart.

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
  "stats": { "all_time": <StatsWindow>, "windows": [<StatsWindow>, ...] },
  "resources": {
    "process": { "rss_bytes": <int>, "cpu_user_seconds": <float>, "cpu_system_seconds": <float> },
    "host": {
      "loadavg_1": <float>, "loadavg_5": <float>, "loadavg_15": <float>,
      "mem_total_bytes": <int>, "mem_available_bytes": <int>,
      "net_rx_bytes_total": <int>, "net_tx_bytes_total": <int>
    }
  }
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
- supports finalize/rerun flags in rest (combinations are rejected):
  -f MESSAGE => finalize_live (MESSAGE is required; stored as commit_message)
  -w ISSUE_ID => finalize_workspace (ISSUE_ID is required; digits only)
  -l => rerun_latest (no extra args)
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
  - finalize_live requires commit_message and builds: runner_prefix + ['-f', commit_message]
  - finalize_workspace requires issue_id (digits) and builds: runner_prefix + ['-w', issue_id]
  - rerun_latest builds: runner_prefix + ['-l']
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
  "commit_summary": "<string>",
  "patch_basename": "<string|null>",
  "raw_command": "<string>",
  "canonical_command": ["<string>", ...],
  "status": "queued|running|success|fail|canceled|unknown",
  "started_utc": "<UTC ISO Z string|null>",
  "ended_utc": "<UTC ISO Z string|null>",
  "return_code": <int|null>,
  "error": "<string|null>",
  "cancel_requested_utc": "<UTC ISO Z string|null>",
  "cancel_ack_utc": "<UTC ISO Z string|null>",
  "cancel_source": "socket|terminate|null"
}

Notes:
- created_utc/started_utc/ended_utc use format "%Y-%m-%dT%H:%M:%SZ".

JobListItem JSON schema (used by Section 7.2.8 GET /api/jobs):
{
  "job_id": "<string>",
  "status": "queued|running|success|fail|canceled|unknown",
  "created_utc": "<UTC ISO Z string>",
  "started_utc": "<UTC ISO Z string|null>",
  "ended_utc": "<UTC ISO Z string|null>",
  "mode": "patch|repair|finalize_live|finalize_workspace|rerun_latest",
  "issue_id": "<string>",
  "commit_summary": "<string>",
  "patch_basename": "<string|null>"

}

Contract:
- GET /api/jobs MUST return JobListItem JSON objects (not JobRecord JSON).
- commit_summary MUST be a single line and use deterministic truncation consistent with Section 2.11.
- patch_basename MUST be filename-only (no directory); it MUST be null if absent.
- GET /api/jobs MUST NOT include additional keys in list items; full details are available via GET /api/jobs/<job_id>.

7.3.3 POST /api/jobs/<job_id>/cancel
Output (success):
{ "ok": true, "job_id": "<string>" }
Error:
- 409 if cannot cancel (unknown job or job already completed)

Cancel semantics (queue.cancel):
- If job.status == "queued":
  - PatchHub sets job.status = "canceled" and sets ended_utc immediately.
- If job.status == "running":
  - Cancel is request-only (Variant 2).
  - PatchHub MUST NOT change job.status or ended_utc.
  - PatchHub records cancel_requested_utc and cancel_source:
    - "socket" when an IPC cancel reply ok is observed
    - "terminate" when it falls back to terminating the process
  - Final status is determined exclusively by runner return_code.

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

7.3.10 POST /api/debug/indexer/force_rescan
Purpose:
- Debug-only trigger for an immediate index rebuild (jobs, runs, ui_snapshot).

Input:
- No body.

Output (success):
{ "ok": true }

Semantics:
- The request handler MUST NOT perform filesystem scanning.
- The handler only signals the background indexer to perform a full rescan.

-------------------------------------------------------------------------------

8. Job Queue, Locking, and Override Injection

8.1 Job IDs
Job IDs are generated by uuid.uuid4().hex (32 lowercase hex characters).

8.2 Persistence
For each job, PatchHub writes:
- jobs_root/<job_id>/job.json
- jobs_root/<job_id>/runner.log (runner stdout/stderr)
Additionally, PatchHub persists a jsonl store into jobs_root/<job_id>/:
- am_patch_issue_<issue_id>.jsonl or am_patch_finalize.jsonl

Persistence source (HARD):
- Runtime source is the runner IPC socket NDJSON stream.
- PatchHub MUST persist every received NDJSON line into the job jsonl store.
- This includes runner events, control frames, and reply frames received on
  the job socket.
- PatchHub MUST NOT rewrite NDJSON lines.
- After receiving a control frame with event="connected", the job event pump
  MUST send the IPC command ready.
- If sending ready fails, or if a reply frame for ready is missing or carries
  ok=false, the pump MUST continue raw capture without aborting the job event
  stream.
- After receiving a control frame with event="eos" and seq=<n>, the job event
  pump MUST first persist that eos line and then send drain_ack(seq=<n>).
- If sending drain_ack fails, or if a reply frame for drain_ack is missing or
  carries ok=false, the pump MUST continue shutdown tail capture without
  dropping already-received lines.

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
- --override ipc_socket_enabled=true
- --override ipc_handshake_enabled=true
- --override ipc_handshake_wait_s=<cfg.runner.ipc_handshake_wait_s>
  - cfg.runner.ipc_handshake_wait_s MUST be an integer >= 1
- --override ipc_socket_path=/tmp/audiomason/patchhub_<job_id>.sock
- --override patch_layout_json_dir=artifacts/web_jobs/<job_id>

PatchHub MUST NOT inject:
- --override json_out=true

Insertion point:
- immediately after the first argv element that ends with "am_patch.py"
- if not found, append at end

Duplicate suppression:
- if an override key already exists in argv, it is not added again

8.5 Completion status mapping
After runner exits:
- return_code == 0 => job.status = "success"
- return_code != 0 => job.status = "fail"

Cancel Variant 2 rule:
- A cancel request MUST NOT change job.status.
- Final status is determined exclusively by return_code.

-------------------------------------------------------------------------------

9. Runner Observation Model (Log + JSONL)

PatchHub provides two complementary streams:
- runner.log (stdout/stderr text) for human reading
- PatchHub jsonl store (am_patch_issue_*.jsonl) for structured UI updates

Runtime source:
- IPC socket NDJSON stream

Persistence:
- PatchHub jsonl store (single pump per job)

SSE (/api/jobs/<job_id>/events) streams JSONL lines by tailing the PatchHub
jsonl store only. PatchHub does not parse or rewrite JSONL lines.
Debug live view requirements (HARD):
- In debug level, the UI MUST display every persisted JSONL line, including
  non-log IPC reply/control frames.
- Debug rendering MUST provide a deterministic non-empty fallback for reply,
  control, and other non-log JSON objects.

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
- UI MUST surface mutation failures to the user using the JSON error envelope
  error string. Silent no-op UI behavior is forbidden.

-------------------------------------------------------------------------------

13. AMP Settings Editor (Runner Configuration)

PatchHub MAY provide a visual editor for the AM Patch runner configuration.

Single source of truth:
- The authoritative configuration is the runner TOML file referenced by:
  cfg.runner.runner_config_toml
- PatchHub must never create or maintain a second configuration store.

API:
- GET /api/amp/schema
  - returns a deterministic schema describing editable runner policy fields
  - schema is derived from the runner Policy surface (dataclass) and is not
    duplicated in PatchHub
  - returns the runner schema export object (schema_version + policy map)
  - PatchHub UI may use label/help metadata when present (non-normative)
- GET /api/amp/config
  - returns current runner policy values (typed)
- POST /api/amp/config
  - body: { "values": {<key>: <value>, ...}, "dry_run": bool }
  - dry_run=true performs validation only and returns typed values
  - dry_run=false validates and then writes the runner TOML atomically
  - MUST reject writes when the runner lock is held (HTTP 409)
  - MUST validate by rebuilding runner Policy from the updated TOML (roundtrip)

UI:
- The AMP Settings editor is located between:
  - A) Start run
  - C) Files
- It is hidden by default (collapsed).
- Field rendering rules:
  - bool -> toggle switch
  - str -> text input
  - int -> numeric input
  - enum -> dropdown
  - list[str] -> tag/chips editor
- Actions:
  - Reload: fetch schema + config
  - Validate: POST with dry_run=true
  - Save: POST with dry_run=false
  - Revert: restore last loaded values

-------------------------------------------------------------------------------

14. Non-Goals

PatchHub is NOT:
- A patch authoring system
- A CI/CD orchestrator
- A replacement for the AM Patch runner
- A general-purpose repository file manager

-------------------------------------------------------------------------------

END OF SPECIFICATION
