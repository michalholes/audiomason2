# AudioMason2 - Wire Contracts Specification (Authoritative)

Specification Version: 1.1.22

This document contains the WIRE layer of the AudioMason2 specification.
It defines HTTP routes and JSON contracts between renderers/clients and the backend.

---

## 9. Web Interface Rules

-   No direct filesystem manipulation outside APIs.

The web UI must be replaceable without touching core logic.

### Debug bundle download (web)

The web interface exposes a debug bundle download endpoint for support
workflows.

-   GET /api/debug/bundle
    -   Query params: logs_tail_lines (default 2000)
    -   Returns: application/zip
    -   The response uses a stable attachment filename:
        audiomason_debug_bundle.zip
    -   The zip contains stable filenames; timestamps appear only in
        manifest.json

The bundle MUST be deterministic: - No timestamped filenames inside the
archive - Stable internal paths across invocations - Runtime timestamps
allowed only inside manifest.json

### 9.0 Web server shutdown output (CLI contract)

When running the web server via the CLI (for example, `audiomason web`),
the CLI MUST emit exactly one shutdown summary line on process exit, in
the following canonical form:

-   Ctrl+C: `Finished (reason: interrupted by user)` with exit code 130
-   Error: `Finished (reason: error: <TypeName>: <message>)` with exit
    code 1
-   Normal return: `Finished (reason: normal exit)` with exit code 0

The literal line `Interrupted.` MUST NOT be printed.

### 9.0.1 Web server quiet mode output (CLI contract)

When running the web server in quiet mode (`audiomason -q web`), console
output MUST be exactly 2 lines and nothing else:

1)  `Starting web server on port 8080...`
2)  `Finished (reason: <...>)`

In quiet mode, uvicorn logging MUST be silenced (no
startup/shutdown/access output). Uvicorn log settings MUST map from AM
verbosity as follows:

-   QUIET: log_level=error, access_log=False
-   NORMAL: log_level=info, access_log=False
-   VERBOSE: log_level=info, access_log=False
-   DEBUG: log_level=debug, access_log=False

In all modes, route-level visibility MUST be provided via deterministic
boundary diagnostics events (boundary.start/boundary.end) rather than
access log spam.

### 9.0.2 Web plugin selection (CLI contract)

When starting web mode, the CLI MUST NOT eager-load all plugins.

Web plugin selection MUST be deterministic and manifest-only:

-   Enumerate only the built-in plugin directories under the repository
    `plugins/` package.
-   Traverse candidate directories in a stable order (sorted by
    directory name).
-   Read `plugin.yaml` using manifest-only loading (no plugin code
    import/execution).
-   Select `web_interface` if present; otherwise fall back to
    `web_server`.

If the selected web plugin fails to load at the call boundary, the CLI
MUST emit a `plugin.load_failed` diagnostics envelope via the Core event
bus and also print a human-readable CLI error.

### 9.1 Web Interface Configuration Surface

The web interface exposes a **UI-only** configuration surface. It must
not create a new source of truth; it only reads and writes through
existing APIs.

Runtime configuration hooks:

-   Config API contract:
    -   `GET /api/am/config` returns:
        -   `config` (nested config object)
        -   `effective_snapshot` (object mapping `key_path` -\>
            `{ value, source }`)
    -   `POST /api/am/config/set` sets a single `key_path` in user
        config.
    -   `POST /api/am/config/unset` unsets a single `key_path` in user
        config (reset to inherit).
    -   Errors from config set/unset must be returned as ASCII-only
        text.
-   Web config UI contract:
    -   Basic configuration: fixed list of common keys (UI hardcoded
        list).
    -   Advanced configuration: full-surface editor over all
        `effective_snapshot` entries.
    -   Advanced supports an 'overrides only' view where
        `source == "user_config"`.
    -   UI does not validate semantics; it only attempts `JSON.parse()`
        and falls back to a string.
-   Common keys:
    -   `web.host`, `web.port`: bind host/port for the HTTP server.
    -   `web.upload_dir`: temporary upload directory used by the web
        server.
    -   `inbox_dir`, `outbox_dir`, `stage_dir`: core filesystem roots
        shown/used by UI.
    -   `logging.level`: canonical logging verbosity (resolved by
        resolver).
    -   `ui.*`: UI theming and UI-related values (project-defined).
-   UI overrides file:
    -   Stored at `~/.config/audiomason/web_interface_ui.json`.
    -   Shape: `{ "nav": [...], "pages": { ... } }`.
    -   Read/write via `/api/ui/config`.
-   Environment variables:
    -   `WEB_INTERFACE_DEBUG`: enable extra diagnostic fields in API
        responses (also enabled when CLI verbosity is "debug").
    -   `WEB_INTERFACE_STAGE_DIR`: override the stage upload directory.

Logs UI:

-   The web server MUST NOT tail a web-specific log file as its primary
    diagnostics source.
-   `/api/logs/stream` and `/api/logs/tail` stream recent
    diagnostics/events from the Core EventBus tap.
-   When runtime diagnostics are enabled (`diagnostics.enabled`), Core
    also writes JSONL at `<stage_dir>/diagnostics/diagnostics.jsonl` and
    the web may expose it via file IO endpoints.

Additional LogBus endpoints:

-   `/api/logbus/stream` and `/api/logbus/tail` stream recent Core log
    records from the in-process LogBus tap.
-   The Logs UI SHOULD prefer LogBus for human-readable log lines and
    MAY also expose EventBus diagnostics.
-   The Logs UI SHOULD auto-scroll to the newest records while a stream
    is active.
-   The Logs UI MUST expose a "Download debug bundle" action that calls
    `GET /api/debug/bundle`.

Developer endpoints:

-   `/api/ui/schema`: returns the current default UI schema and the
    configuration hooks above.

Debug JS page (debug-only):

-   When `WEB_INTERFACE_DEBUG` is enabled, the web UI MAY expose a Debug
    JS page at route `/debug-js`.
-   The page is UI-only and displays JavaScript errors captured
    in-session from `window.onerror` and `unhandledrejection`.
-   Error capture MUST be fail-safe and MUST NOT replace or overwrite
    the UI when an error occurs.

Debug mode UI transparency (debug-only):

-   When `WEB_INTERFACE_DEBUG` is enabled, the web UI MUST surface
    browser-side debug information through the UI.
-   In debug mode, HTTP requests that receive a non-2xx response MUST
    emit a client-side debug record that includes at least: timestamp,
    method, URL/path, HTTP status, response body (truncated), and a
    callsite stack trace.
-   The Logs UI MUST include a client-side debug feed in debug mode, so
    a user can diagnose HTTP conflicts/errors without using browser
    DevTools.
-   In debug mode, non-2xx HTTP responses MUST trigger an immediate UI
    notification (toast or modal) with the status and basic context.

### 9.2 Root browsing

The web UI may browse only an allowlisted set of file roots exposed by
the backend.

-   The backend MUST expose `GET /api/roots`.
-   The response MUST include only user-facing roots: `inbox`, `stage`,
    `jobs`, `outbox`.
-   The `jobs` root may be hidden via config key
    `web_interface.browse.show_jobs_root` (default: true).
-   Path traversal MUST be rejected (no `..` segments) in all file
    browsing inputs.

--

------------------------------------------------------------------------

------------------------------------------------------------------------

## 10.4 Wire Contracts (FlowConfig, FlowModel, SessionState, Errors)

This section defines the stable JSON contracts between renderers and the import engine.

### 10.4.1 Error JSON (Mandatory)

All validation and invariant failures MUST return:

{
  "error": {
    "code": "VALIDATION_ERROR" | "INVARIANT_VIOLATION" | "NOT_FOUND" | "CONFLICTS_UNRESOLVED" | "INTERNAL_ERROR",
    "message": "Human-readable summary (ASCII-only)",
    "details": [
      { "path": "<json-path>", "reason": "<reason-code>", "meta": { ... } }
    ]
  }
}

### 10.4.2 Selection Expression Grammar (Mandatory)

For multi_select_indexed fields, renderers MAY submit either:
- Expression form: { "<field>_expr": "all" | "1,3,5-8" }
- Explicit IDs form: { "<field>_ids": ["id1", "id2"] }

Grammar (informal):
- selection := "all" | segment ("," segment)*
- segment := number | range
- range := number "-" number
- number := [1-9][0-9]*

Rules:
- Whitespace is ignored.
- Ranges are inclusive; "5-5" is valid.
- Duplicates are removed.
- Out-of-range indices MUST yield VALIDATION_ERROR.
- The resulting ID list MUST preserve the original item ordering (stable selection).

### 10.4.3 Field Types (Baseline)

Supported field types (baseline):
- text
- toggle
- confirm
- select
- number
- multi_select_indexed
- table_edit

Field definitions MUST declare required properties appropriate for their type (engine is authoritative).

### 10.4.4 FlowConfig (Versioned)

FlowConfig is the editable configuration for optional steps and defaults. It MUST be versioned and validated.

FlowConfig controls ONLY:
- enabled/disabled state of optional steps
- default values for inputs
- UI preferences (preview limits, collapse defaults)
- presets and history governance (if implemented)

FlowConfig MUST NOT change:

FlowConfig MUST NOT include a top-level conflicts key.
Conflict policy is provided via the conflict_policy step and stored in SessionState.conflicts.

- PHASE numbers and boundaries
- mandatory steps existence
- ordering invariants
- conflict resolution placement rules
- processed registry semantics
- job creation semantics

### 10.4.5 FlowModel (Runtime)

FlowModel is generated at runtime from FlowConfig and a single BaseFlowDefinition.
Renderers MUST treat FlowModel as the single source of truth for rendering.

FlowModel includes:
- flow_id
- steps[] where each step includes:
  - step_id
  - title
  - phase
  - required
  - fields[] with type-specific properties

For multi_select_indexed fields, the engine MUST provide a concrete items[] list in the
effective_model.json snapshot for the active session.

For the mandatory selection steps:
- select_authors items MUST be derived deterministically from discovery.json.
- select_books items MUST be derived deterministically from discovery.json.

Each item MUST include:
- item_id (stable, opaque id)
- label (ASCII-only, human-readable)
- display_label (Unicode, human-readable; renderer-preferred when present)

Renderers SHOULD prefer display_label when present and fall back to label.

### 10.4.6 SessionState (Runtime)

SessionState is returned to renderers after each operation and contains at minimum:
- session_id
- current_step_id
- answers (canonicalized inputs)
- computed (engine-produced computed data)
- selected_author_ids
- selected_book_ids
- effective_author_title (per-book mapping when applicable)

ERR submissions MUST NOT mutate answers except safe normalization.

## 10.5 Import Plugin API (UI-Facing Routes)

All routes are owned by the import plugin.

Baseline routes:

1) GET  /import/ui/flow
   - Returns FlowModel JSON for the current configuration.

2) GET  /import/ui/config
   - Returns the current FlowConfig.
   - Response body:
     { "config": <FlowConfig> }

3) POST /import/ui/config
   - Validates, normalizes, and persists FlowConfig (full replace).
   - Request body:
     { "config": <FlowConfig> }
   - Contract requirements:
     - config is REQUIRED
     - Unknown request body fields MUST be rejected
     - Any contract violation MUST return HTTP 400 with VALIDATION_ERROR (10.4.1)
   - Returns the saved canonical FlowConfig:
     { "config": <FlowConfig> }
   - On error returns the Error JSON schema (10.4.1).

4) POST /import/ui/config/validate
   - Validates and normalizes FlowConfig without persisting.
   - Request body:
     { "config": <FlowConfig> }
   - Contract requirements:
     - config is REQUIRED
     - Unknown request body fields MUST be rejected
     - Any contract violation MUST return HTTP 400 with VALIDATION_ERROR (10.4.1)
   - Returns canonical normalized FlowConfig:
     { "config": <FlowConfig> }

5) POST /import/ui/config/reset
   - Resets FlowConfig to built-in defaults.
   - Persists and returns the FlowConfig:
     { "config": <FlowConfig> }

6) GET  /import/ui/config/history
   - Returns the last 5 persisted FlowConfig versions (newest-first).
   - Response body:
     {
       "items": [
         { "id": "string", "timestamp": "ISO-8601" }
       ]
     }

7) POST /import/ui/config/rollback
   - Rolls back FlowConfig to a prior version and persists it.
   - Request body:
     { "id": "string" }
   - Contract requirements:
     - id is REQUIRED
     - Unknown request body fields MUST be rejected
     - Any contract violation MUST return HTTP 400 with VALIDATION_ERROR (10.4.1)
   - If id is not found MUST return HTTP 404 with Error code NOT_FOUND (10.4.1).
   - Response body:
     { "config": <FlowConfig> }

8) GET  /import/ui/wizard-definition
   - Returns the current WizardDefinition.
   - Response body:
     { "definition": <WizardDefinition> }

9) POST /import/ui/wizard-definition
   - Validates and persists WizardDefinition (full replace).
   - Request body:
     { "definition": <WizardDefinition> }
   - Contract requirements:
     - definition is REQUIRED
     - Unknown request body fields MUST be rejected
     - Any contract violation MUST return HTTP 400 with VALIDATION_ERROR (10.4.1)
   - Returns the saved WizardDefinition:
     { "definition": <WizardDefinition> }
   - Engine invariant violations MUST return INVARIANT_VIOLATION (10.4.1).

10) POST /import/ui/wizard-definition/validate
   - Validates WizardDefinition without persisting.
   - Request body:
     { "definition": <WizardDefinition> }
   - Contract requirements:
     - definition is REQUIRED
     - Unknown request body fields MUST be rejected
     - Any contract violation MUST return HTTP 400 with VALIDATION_ERROR (10.4.1)
   - Returns canonical WizardDefinition:
     { "definition": <WizardDefinition> }
   - Engine invariant violations MUST return INVARIANT_VIOLATION (10.4.1).

11) POST /import/ui/wizard-definition/reset
   - Resets WizardDefinition to built-in defaults.
   - Persists and returns the WizardDefinition:
     { "definition": <WizardDefinition> }

12) GET  /import/ui/wizard-definition/history
   - Returns the last 5 persisted WizardDefinition versions (newest-first).
   - Response body:
     {
       "items": [
         { "id": "string", "timestamp": "ISO-8601" }
       ]
     }

13) POST /import/ui/wizard-definition/rollback
   - Rolls back WizardDefinition to a prior version and persists it.
   - Request body:
     { "id": "string" }
   - Contract requirements:
     - id is REQUIRED
     - Unknown request body fields MUST be rejected
     - Any contract violation MUST return HTTP 400 with VALIDATION_ERROR (10.4.1)
   - If id is not found MUST return HTTP 404 with Error code NOT_FOUND (10.4.1).
   - Response body:
     { "definition": <WizardDefinition> }

14) POST /import/ui/session/start
   - Body: { "root": "<root-name>", "path": "<relative-path>", "mode": "stage" | "inplace" }
   - Contract requirements:
     - root, path, and mode are REQUIRED (no implicit defaults)
     - mode MUST be one of: stage, inplace
     - Unknown request body fields MUST be rejected
     - Any contract violation MUST return HTTP 400 with VALIDATION_ERROR (10.4.1)
   - Starts a new wizard session and returns SessionState.

15) GET  /import/ui/session/{session_id}/state
   - Returns SessionState for an existing session.

16) POST /import/ui/session/{session_id}/step/{step_id}
   - Submits a step payload and returns updated SessionState.

17) POST /import/ui/session/{session_id}/start_processing
   - Body: { "confirm": true }
   - Finalizes PHASE 1 and returns a summary: { "job_ids": [...], "batch_size": <int> }
   - MUST enforce deterministic conflict re-check before job creation (10.11.4).

All editor history and rollback behavior MUST be deterministic and atomic.
## 10.6 Engine Guards (Invariants; MUST REJECT)

The engine MUST reject any WizardDefinition, FlowConfig, or effective workflow construction that attempts to:

- remove mandatory steps (10.3.2)
- violate mandatory ordering constraints (10.3.2)
- remove final_summary_confirm
- remove conflict_policy
- remove processing (PHASE 2 terminal)
- change PHASE numbers
- allow start_processing before conflict resolution when conflict_mode == "ask"
- mark processed registry before job success
- insert steps before select_authors
- insert steps after processing
- bypass resolve_conflicts_batch when conflict_mode == "ask" and conflicts exist

Rejection MUST use INVARIANT_VIOLATION (10.4.1).

## 10.18 Step Payload Contract (Renderer Interface)

The interpreter MUST return the following canonical structure:

{
  "session_id": "string",
  "current_step": "step_id",
  "type": "select | input | transform | action | review | finalize",
  "data": {},
  "allowed_actions": [],
  "errors": [],
  "action_status": {
    "state": "idle | running | failed | completed",
    "details": {}
  }
}

Renderers MUST render strictly from this payload.

No UI-specific branching is permitted.

------------------------------------------------------------------------

## 10.19 Plugin Operation Discovery (Registry-Mediated Only)

Callable operations MUST be discovered exclusively via PluginRegistry.

Registry metadata MUST include:

{
  "plugin_id": "string",
  "wizard_callable_manifest_pointer": {
    "type": "file",
    "path": "relative/path/to/manifest.json"
  }
}

The interpreter SHALL:

1. Query PluginRegistry.
2. Load callable manifest via wizard_callable_manifest_pointer.
3. Validate manifest.
4. Expose operations via list_callable_operations().

Filesystem scanning is forbidden.

------------------------------------------------------------------------

## 10.20 Callable Plugin Manifest Contract


Clarification:
- "plugin manifest config_schema" in Section 7.1.2 refers to configuration normalization schema.
- The "callable plugin manifest" defined here is a separate contract for wizard-callable operations.
- A plugin MAY choose to store both contracts in one physical JSON file, but the registry MUST expose
  wizard-callable operations through wizard_callable_manifest_pointer and the interpreter MUST validate
  the callable contract independently.

Each callable plugin MUST provide a manifest with:

{
  "plugin": "string",
  "manifest_version": 1,
  "operations": [
    {
      "name": "string",
      "execution": "inline | job",
      "input_schema": {},
      "result_schema": {},
      "limits": {
        "timeout_seconds": integer,
        "max_result_bytes": integer
      }
    }
  ]
}

Interpreter MUST enforce:

- Input validation
- Limit enforcement
- Result validation

Execution type:

- inline: executed within PHASE 1 under interpreter control
- job: MUST generate a PHASE 1 action job request (sessions/<session_id>/action_jobs.json) and use the existing Job subsystem; PHASE 2 processing remains governed by 10.11

Interpreter MUST NOT implement parallel job execution mechanism outside Section 5.

------------------------------------------------------------------------

## 10.21 Formal Session Lifecycle Extension

Session states:

- CREATED
- ACTIVE
- WAITING_FOR_ACTION
- ERROR
- COMPLETED
- FINALIZED

FINALIZED sessions MUST be immutable:

- effective_workflow frozen
- state frozen
- job_requests immutable
- diagnostics append-only

Mutation after FINALIZED MUST be rejected.

------------------------------------------------------------------------

## 10.22 Expression Model (Sealed)

Expressions allowed in WizardDefinition are restricted to pure data lookup:

Allowed forms:

- $state.<path>
- $step.<step_id>.output.<path>

Rules:

- No scripting
- No conditionals
- No dynamic evaluation
- No computed expressions
- Invalid reference MUST raise VALIDATION_ERROR
- Expression resolution MUST be side-effect free

Embedding general-purpose expression engines is forbidden.

------------------------------------------------------------------------

## 10.23 Preview Execution (Optional, Isolated)

Interpreter MAY support preview_action().

Preview rules:

- Uses same validation as real action
- Does NOT modify session snapshot
- Does NOT create job_requests
- Emits diagnostics
- Stored under:

<wizards_root>/import/previews/<preview_id>.json

Preview artifacts MUST be isolated and disposable.

------------------------------------------------------------------------

## 10.24 Determinism Guarantees (Extended)

Interpreter MUST guarantee:

- Stable selection ordering
- No hidden mutable state
- Same inputs + same effective_workflow -> identical outputs
- Preview does not alter session determinism

------------------------------------------------------------------------

## 10.25 CI-Enforced Anti-Drift Rules

The repository MUST enforce automated checks ensuring:

1. UI layers do not import plugin execution modules.
2. Only interpreter executes plugin operations.
3. No step_id branching in UI.
4. CLI and Web render identical payload for identical session state.
5. Deterministic snapshot tests pass.
6. Malformed manifest is rejected before exposure.

------------------------------------------------------------------------

Integration completed (updated): 2026-02-19 00:00:00 UTC
---------------------------------------------------------------------
## Plugin-Owned UI Architecture

### 1. Normative Rule

A plugin MAY host its own Web UI implementation.

If a plugin exposes a UI-facing FastAPI router (e.g. `/import/ui/*`),
it MAY additionally serve:

- an HTML entrypoint under the same prefix (e.g. `/import/ui/`)
- static assets under `/import/ui/assets/*`

This makes the plugin self-sufficient and portable across different
web hosts.

### 2. Responsibility Model

If a plugin owns its UI:

- The plugin is responsible for rendering all field types used by
  its wizard/model.
- The plugin MUST NOT rely on host-specific UI renderers.
- The host (e.g. web_interface) MUST treat the plugin UI as an
  opaque consumer route and MUST NOT re-implement its renderer logic.

This prevents renderer drift and preserves CLI/Web parity within
the plugin boundary.

### 3. Directory Structure

If a plugin owns its UI, the following structure is normative:

    plugins/<plugin>/ui/
        web/
            index.html
            assets/
        cli/
        tui/

The presence of `web/` indicates that the plugin serves its own
web interface.
