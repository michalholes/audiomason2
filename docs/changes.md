## 2026-03-09T00:00:02+01:00

- Sync the AMP runner docs with the implemented failure-detail contract and
  current RUNNER_VERSION example.

## 2026-03-09T00:00:01+01:00

- Emit runner-owned ERROR DETAIL records for RunnerError failures, keep the
  FAIL summary fixed, and guarantee failure fingerprints in the file log.

## 2026-03-09T00:00:00+01:00

- Define runner-owned failure detail records for RunnerError failures, keep
  the FAIL final summary shape fixed, and require failure fingerprint blocks
  in the file log.

## 2026-03-08T00:00:03+01:00

-   Issue 118: strip WizardDefinition editor-only `_am2_ui` metadata from the
    v3 registry wire payload so Validate/Save/Save All work again without
    weakening backend strict validation.

## 2026-03-08T00:00:02+01:00

-   Issue 117: close the v3 dream editor/import work with end-to-end Phase II
    acceptance coverage, Phase II next-run draft activation coverage, and
    explicit v2/v3 default-selection coexistence tests.

## 2026-03-08T00:00:01+01:00

-   Issue 116: add Phase II visual editor authoring for `parallel.fork_join@1`,
    `flow.invoke@1`, `flow.loop@1`, and file-local libraries while keeping
    Raw JSON authoritative and preserving unknown valid keys across visual edits.

## 2026-03-08T00:00:00+01:00

-   Issue 115: implement the import DSL Phase II runtime for
    `parallel.fork_join@1`, `flow.invoke@1`, `flow.loop@1`,
    file-local libraries/macros, Raw JSON Phase II execution, and
    deterministic FlowModel projection and runtime trace ordering.

## 2026-03-07T00:00:07+01:00

-   Issue 114: define Phase II import DSL capabilities for
    `parallel.fork_join@1`, `flow.invoke@1`, `flow.loop@1`,
    file-local libraries/macros, deterministic FlowModel projection,
    SessionState bookkeeping, and editor authoring boundaries.
-   spec: Bump specification version to 2.0.11-normalized-m1.

## 2026-03-07T00:00:07+01:00

-   Issue 113: make the v3 import bootstrap default independent of CLI
    launcher mode, noninteractive mode, and nav_ui, while preserving
    explicit v2 artifact dispatch for coexistence.

-   Issue 113: harden the Issue 110 Node/VM editor harnesses with bounded
    traversal and subprocess timeouts so inconsistent UI code fails
    deterministically instead of hanging pytest.

## 2026-03-07T00:00:06+01:00

-   Issue 110 corrective: restore inline :back/:cancel handling for v3
    prompt-mode CLI steps so existing v3 definitions abort or rewind
    immediately instead of requesting extra prompts.

## 2026-03-07T00:00:05+01:00

-   Issue 500: define PatchHub post-exit grace semantics for bounded stdout
    tail drain and IPC shutdown-tail completion without changing return_code
    status mapping.

-   Issue 500: add runner.post_exit_grace_s to PatchHub TOML and bump the
    PatchHub runtime version to 1.8.1.

## 2026-03-07T00:00:04+01:00

-   Issue 112: harden the default v3 import path by restoring legacy
    selection mirrors for the bootstrap steps, forcing plan preview state
    refresh after the automatic preview hop, and adding coexistence,
    editor-next-run, and acceptance coverage.

## 2026-03-07T00:00:03+01:00

-   Issue 111: add a Python-defined v3 default import program for the CLI
    bootstrap path, keep explicit v2 artifact dispatch unchanged, and
    preserve inline-nav CLI behavior by limiting the v3 default path to
    prompt-mode launcher sessions.

## 2026-03-07T00:00:02+01:00

-   Issue 110: add first-class prompt primitive authoring controls to the
    v3 web editor, keep Raw JSON authoritative, and keep ui.message@1
    non-interactive in the editor.

## 2026-03-07T00:00:01+01:00

-   Issue 109: add CLI/Web runtime parity for v3 prompt metadata, ship a
    dedicated web v3 renderer, and keep autofill/backend-driven prompt
    advancement renderer-neutral.

## 2026-03-07T00:00:00+01:00

-   Issue 108: project baseline prompt metadata into FlowModel v3 ui,
    normalize prompt runtime metadata in step APIs, and add PHASE 1
    autofill auto-advance for v3 prompt primitives.

## 2026-03-06T00:00:02+01:00

-   Issue 107: define v3 prompt metadata keys in op.inputs, FlowModel ui projection, prompt metadata eval order, and ui.message@1 prompt-metadata exclusion.
-   spec: Bump specification version to 2.0.9-normalized-m1.

## 2026-03-06T00:00:01+01:00

-   Issue 105 corrective: remove the parallel.map@1 write drift in the v3 runtime
    so non-empty writes remain allowed, fail only on duplicate to_path
    conflicts, and replace the drift test with conflict-vs-non-conflict
    coverage.

## 2026-03-06T00:00:00+01:00

-   Issue 105: remove v3 baseline select_authors drift, normalize v3 trace results to OK/ERR, stop implicit prompt answers/inputs writes, enforce parallel.map write conflict guard, and raise trace retention to 1000 events.
-   Issue 106: remove hidden v3 editor write defaults, keep write rows neutral with empty to_path, and trim boot_v3.js below the monolith gate threshold.

-   Issue 104: Define baseline DSL primitive semantics v1 (prompt payloads, output keys, stop/job semantics, and parallel.map merge baseline).
-   spec: Bump specification version to 2.0.8-normalized-m1.

## 2026-03-05T00:00:00+01:00

-   spec: Define WizardDefinition v3 as a DSL program model (primitive invocations, single-file JSON).
-   spec: Define FlowModel kind gating for legacy v2 vs DSL v3.
-   spec: Define SessionState namespaces and state-path conventions for the DSL interpreter.
-   spec: Define import wizard primitive registry artifact and baseline expression operators/functions.
-   spec: Bump specification version to 2.0.6-normalized-m1.
-   Issue 101: Define WizardDefinition v3 wire schema (nodes, edges, ExprRef, writes).
-   Issue 101: Define primitive_registry.json wire schema (restricted JSON-Schema subset).
-   Issue 101: Define SessionState trace event shape and deterministic bounds.
-   Issue 101: Define deterministic parallel semantics for DSL primitives.
-   spec: Bump specification version to 2.0.7-normalized-m1.

## 2026-03-03T00:00:00+01:00

-   Issue 23: Import wizard editor now enforces mandatory ordering constraints for
    WizardDefinition v2 (graph.nodes order) at validate/save/activate time, and
    runtime load self-heals invalid active definitions by resetting to defaults.

-   spec: Bump specification version to 2.0.2-normalized-m1.


-   spec: Define strict power flow editing governance (authoritative workflow,
    deterministic merge, operator registry, strict error reasons, pinned constraints,
    and baseline_type change policy).

-   spec: Bump specification version to 2.0.3-normalized-m1.

-   spec: Define import plugin power flow editing surface (editable StepSchema, runtime defaults keys,
    strict value precedence, canonical transition operators, and pinned constraint transparency).

-   spec: Add project-wide governance and validation stabilizers (strict precedence, canonical
    operator registry, unknown field/path policy, idempotent evaluation, alias governance,
    extension discoverability, and optional conformance vectors).

-   spec: Bump specification version to 2.0.4-normalized-m1.

-   spec: Strengthen architecture guarantees by binding capability surfaces and
    value precedence to implementations, version-locking the canonical operator
    registry, isolating extensions from structural validation, requiring explicit
    alias migration on removal, and requiring deterministic operator semantics.

-   spec: Bump specification version to 2.0.5-normalized-m1.

## 2026-03-02T00:00:00+01:00

-   Issue 10000: spec: Normalize docs/specification.jsonl by marking duplicate rules as
    alias -> canonical_id (with status/supersedes metadata), and mark JSON-snippet
    rule entries as invalid. Bump JSONL spec version to 2.0.1-normalized-m1.

## 2026-03-01T00:00:00+01:00

- spec/tooling: Replace gates_on_partial_apply/gates_on_zero_apply with apply_failure_*_gates_policy (defaults: repair_only/never).

## 2026-02-26T00:00:00+01:00

- Issue 267: Import UI Flow Editor - row click selects step, drag handle grip for reorder, and per-row actions reduced to trash only.
- Issue 268: Flow Editor - eliminate remaining deficiencies: migrate WizardDefinition v1 to v2 (graph),
  enforce v2 at runtime and editor API, and fix deterministic icon/CSS wiring.
- Import UI: WizardDefinition editor now ensures graph (version 2) on reload to keep transitions available.

## 2026-02-24T22:00:00+01:00

-   Issue 259: Refactor Import UI Flow Editor layout from overlay panels to a
    deterministic grid-based sidebar with explicit tabs.
-   spec: Bump specification version to 1.1.28.

## 2026-02-24T18:00:00+01:00

-   spec: Allow Unified Flow Editor (single screen) for WizardDefinition + FlowConfig,
    preserving governance boundaries.
-   Import UI: add GET /import/ui/steps/{step_id} (read-only step details for UI rendering).
-   spec: Bump specification version to 1.1.26.

## 2026-02-24T00:00:00+01:00

-   Import UI: add GET /import/ui/steps-index (read-only palette for visual wizard editor).

## 2026-02-23T21:45:00+01:00

-   Issue 238: Import CLI editor now exposes explicit FlowConfig and WizardDefinition editor areas.
-   Issue 238: Legacy editor catalog/flow edit/save commands remain callable but fail explicitly as immutable.
-   spec: Bump specification version to 1.1.23.


## 2026-02-23T19:00:00+01:00

-   spec: Make layered documents under docs/spec/ the only authoritative specification.
-   spec: Reduce docs/specification.md to a non-normative overview stub.
-   spec: Bump specification version to 1.1.22.


## 2026-02-23T17:00:00+01:00

-   Issue 237: Import UI session state now includes effective_model, and the web wizard renders steps from the session snapshot after session start.

## 2026-02-23T09:30:00+01:00

-   spec: Split the specification into layered documents under docs/spec/ (ARCH/WIRE/LAYOUT).

-   spec: Bump specification version to 1.1.20.

## 2026-02-23T00:30:00+01:00

-   Issue 233: /import/ui/session/start now enforces strict request body validation (root/path/mode required, mode enum enforced, unknown fields rejected; no defaults).

-   spec: Bump specification version to 1.1.19 and document strict session/start validation.

## 2026-02-21T21:00:00+01:00

-   Issue 229: Import CLI suppresses high-volume internal INFO logs on the interactive console in normal verbosity (LogBus unchanged; warnings/errors remain visible).

-   spec: Bump specification version to 1.1.16 and add a normative console output policy for the import launcher.

## 2026-02-20T23:00:00+01:00

-   Issue 222: Import discovery canonical ordering now sorts by UTF-8 byte order
    (root, relative_path, kind) to remain deterministic with non-ASCII inputs.

## 2026-02-20T17:00:00+01:00

-   Issue 220: Import UI config endpoints now delegate to engine-owned APIs (get/set/reset) and no longer access engine internals or filesystem helpers.

-   Issue 220: start_processing rereads job_requests.json after writing to guarantee the persisted idempotency_key is used for job creation.

-   Issue 220: Import plugin now maintains a processed books registry updated only on successful import PROCESS job completion (diag.job.end status=succeeded).

-   Issue 220: Add unit tests for UI config delegation, idempotency reread, processed registry updates, and plugin boot behavior when the import plugin is absent.

-   spec: Bump specification version to 1.1.14.

## 2026-02-19T18:30:00+01:00

-   Issue 212: Import wizard session state now includes canonical fields
    (answers/computed/selected_* and effective_author_title) and compute_plan
    writes plan_summary into state.computed.

-   Issue 212: /import/ui/config/reset now resets FlowConfig to the builtin
    DEFAULT_FLOW_CONFIG and returns the normalized, validated config.

-   Issue 212: Import CLI renderer now finalizes the wizard by calling
    start_processing(confirm=true) and prints job_ids and batch_size.

## 2026-02-19T00:45:00+01:00

-   spec: Fully integrate WizardDefinition structural workflow authority into Import Wizard specification (no addendum).
-   spec: Introduce single Interpreter authority model with canonical Step Payload contract.
-   spec: Define registry-mediated callable plugin manifest discovery (manifest_pointer required in PluginRegistry).
-   spec: Formalize action execution contract (inline vs job) and require integration with existing Job subsystem.
-   spec: Add formal session lifecycle state machine (CREATED→ACTIVE→WAITING_FOR_ACTION→ERROR→COMPLETED→FINALIZED).
-   spec: Enforce FINALIZED snapshot immutability.
-   spec: Seal expression model (lookup-only; no scripting).
-   spec: Define preview_action isolation rules and preview artifact storage.
-   spec: Add CI-enforced anti-drift invariants (UI isolation, determinism, parity tests).
-   spec: Bump specification version to 1.1.8.

## 2026-02-19T00:31:56+01:00

-   import: Treat .rar archives as bundle sources during PHASE 0 discovery.
-   spec: Document PHASE 0 bundle extension list includes .rar; bump specification version to 1.1.7.

## 2026-02-18T23:25:46+01:00

-   plugins: Add interactive CLI renderer launcher for Import Wizard (`audiomason import`)
    with resolver-based configuration and CLI overrides.
-   spec: Define Import CLI launcher/renderer configuration keys and precedence rules.
-   spec: Bump specification version to 1.1.6.

## 2026-02-18T08:53:20+00:00

-   spec: Require job_requests.json to include config_fingerprint (SHA-256 over canonical effective_config.json).
-   spec: Make FlowConfig history retention N=5 mandatory when history/rollback is implemented.
-   spec: Bump specification version to 1.1.4.

## 2026-02-18T08:15:00+01:00

-   spec: Define mandatory bootstrap of Import Wizard catalog/flow models when missing under file_io wizards root.
-   spec: Bump specification version to 1.1.3.

## 2026-02-18T07:00:00+01:00

-   spec: Fully integrate Import Wizard consolidated model (V3-V11) into Section 10, including authoritative state machine, wire-level JSON contracts, renderer neutrality enforcement, idempotency rules, conflict re-check before job creation, canonical serialization requirements, snapshot isolation, config governance, performance constraints, and mandatory deterministic test gates.
-   spec: Replace previous Section 10 with consolidated authoritative definition (no partial layering).
-   spec: Bump specification version to 1.1.2.

## 2026-02-18T00:00:00+01:00

-   plugins: Define canonical host config key-space for per-plugin configuration and materialize missing schema defaults during plugin load without overwriting user values.
-   api: Stop using "~/.config/audiomason/plugins.yaml" for plugin state/config; use PluginRegistry and host config only.
-   spec: Document plugin config normalization behavior and mark plugins.yaml obsolete; bump specification version to 1.1.1.

## 2026-02-17T16:29:35+01:00

-   spec: Integrate consolidated Import Wizard model (data-defined Step
    Catalog, FlowModel, deterministic discovery, effective config
    snapshot, fingerprint closure, job request contract, filesystem
    isolation, upgrade/migration rules).
-   spec: Introduce determinism closure tuple (model_fingerprint +
    discovery_fingerprint + effective_config_fingerprint + validated
    inputs).
-   spec: Define canonical JSON persistence rules and SHA-256
    fingerprinting requirements.
-   spec: Formalize PHASE 0 discovery ordering and item_id derivation.
-   spec: Formalize session freeze semantics (no silent upgrade of
    in-progress sessions).
-   spec: Bump specification version to 1.1.0.

## 2026-02-17T13:00:00+01:00

-   Issue 601: Remove Import Wizard (API + UI) from web_interface
    plugin.
-   tests: Update web tests to expect no import endpoints and no Import
    nav entry.
-   spec: Remove Web Import Wizard canonical specification (web import
    is not implemented).

## 2026-02-16T01:10:00+01:00

-   Issue 603: Fix import CLI wizard PHASE 1 completeness and branching
    (mode selection, lookup toggle,
    filename/covers/ID3/audio/publish/delete/conflict options).
-   Issue 603: Default CLI run is quiet (prompts + summaries only).
-   tests: Add unit coverage for Issue 603 PHASE 1 prompt order and
    audio branching.
-   spec: Document import CLI PHASE 1 global_options keys; bump
    specification version to 1.0.86.

## 2026-02-16T00:30:00+01:00

-   Issue 399: Rename built-in CLI host plugin from `cli` to
    `cmd_interface` (breaking; no config migration).
-   spec: Document cmd_interface as the built-in CLI host plugin and
    bump specification version to 1.0.85.

## 2026-02-15T20:13:00+01:00

-   import: Make external lookup non-blocking in preflight (background
    lookup; no asyncio.run).
-   spec: Clarify PHASE 0 rule: no source mutations, but best-effort
    JOBS cache writes are allowed (user-approved).

  ---------------------------------------------------------------------
  2026-02-15 --- Import Wizard Specification Refactor

  \- Consolidated full Import Wizard definition into
  docs/specification.md. - Removed legacy CLI-specific and AM1-like
  wizard sections. - Eliminated duplicate wizard behavior
  definitions. - Established single canonical source of truth for
  Import Wizard. - Cleaned specification to remove
  implementation-layout references.
  ---------------------------------------------------------------------

## 2026-02-15T08:10:00+01:00

-   Issue 700: CLI import wizard: Fast Index first (immediate
    authors/books), then mandatory plan/preview after book selection
    (author/title confirmation + rename preview) before Start.
-   Issue 700: Fix CLI import dynamic service import to accept
    `ImportEngineService` (compat) when module does not expose
    `import_engine_service_cls`.
-   Issue 700: Fix CLI import dynamic type lookup to use exported
    classes (`BookDecision`, `ImportJobRequest`, `ImportRunState`).
-   spec: Document fast-index-first + plan/preview CLI flow and bump
    specification version to 1.0.82.

## 2026-02-15T07:50:00+01:00

-   Issue 523: import_wizard UI: Auto-advance after Start only when the
    Start call succeeds without conflict resolution (no HTTP 409 in the
    Start attempt).
-   spec: Clarify conflict-sensitive auto-advance trigger and bump
    specification version to 1.0.81.

## 2026-02-15T00:35:00+01:00

-   Issue 522: import_wizard API: Ensure PHASE 0 deep enrichment uses
    best-effort external lookup by default across all wizard entrypoints
    (/preflight and /start), not only the background deep scan.
-   spec: Clarify that Web Import Wizard lookup default applies to all
    preflight/deep enrichment API paths and bump specification version
    to 1.0.80.

## 2026-02-15T00:25:00+01:00

-   Issue 521: import: Ensure PHASE 0/2/processed_registry use a single
    canonical fingerprint key builder name and explicitly forbid
    full-file hashing for identity (stat-signature only).
-   spec: Add explicit implementation note for the shared fingerprint
    builder and bump specification version to 1.0.79.

## 2026-02-15T00:10:00+01:00

-   Issue 520: import_wizard API: Ensure processed_registry always
    returns keys: list\[str\] for UI compatibility, including when
    registry outputs are dict-shaped (defensive compatibility).
-   spec: Clarify processed_registry keys as authoritative field for UI
    loaders and bump specification version to 1.0.78.

## 2026-02-14T23:31:10+01:00

-   Issue 516: import_wizard API: Ensure preflight books include
    fingerprint and rename_preview when available (schema parity with
    index).
-   spec: Document preflight schema parity and bump specification
    version to 1.0.77.

## 2026-02-14T23:59:30+01:00

-   Issue 515: import_wizard UI: After successful Start (HTTP 200/202),
    auto-advance selection to the next actionable book (deterministic
    author/book order).
-   Issue 515: import_wizard UI: Do not auto-advance when Start is not
    successful (including 409 conflicts requiring user action).
-   spec: Clarify success-only auto-advance trigger and bump
    specification version to 1.0.76.

## 2026-02-14T23:59:00+01:00

-   Issue 514: import_wizard: Ensure PHASE 0 deep enrichment enables
    external lookup by default in the Web Import Wizard context
    (explicit flag), while remaining strictly best-effort and fail-safe.
-   import: Default external lookup to OFF outside the Web Import Wizard
    context.
-   spec: Clarify lookup defaults and bump specification version to
    1.0.75.

## 2026-02-14T23:55:00+01:00

-   Issue 513: import: Ensure PHASE 2 import identity keys never rely on
    full-file hashing and remain unified with PHASE 0 preflight
    fingerprints and processed_registry keys (single stat-based
    builder).
-   spec: Clarify fingerprint key form `<algo>:<value>` and that
    `sha256` refers to the stat signature (not file contents); bump
    specification version to 1.0.74.

## 2026-02-14T23:40:00+01:00

-   Issue 512: import_wizard API: Make processed_registry response
    schema stable and UI-compatible by always returning keys:
    list\[str\] of processed fingerprint keys (items/count remain for
    compatibility).
-   spec: Document processed_registry response example and bump
    specification version to 1.0.73.

## 2026-02-14T21:20:00+00:00

-   Issue 511: import_wizard UI: After successful Start, auto-advance to
    next actionable book (deterministic author/book order), default ON
    with UI toggle.
-   spec: Document Import Wizard auto-advance rule and bump
    specification version to 1.0.72.

## 2026-02-14T21:10:57+00:00

-   Issue 510: import_wizard UI: Drive processed state strictly from
    fingerprint keys in processed_registry (gray-out, disable Start,
    Unmark).
-   Issue 510: import_wizard UI: Unmark refreshes processed state
    immediately.
-   spec: Clarify processed_registry UI matching (fingerprint-only) and
    bump specification version to 1.0.71.

## 2026-02-14T20:57:03+00:00

-   Issue 509: import_wizard: Enable best-effort external metadata
    lookup by default during PHASE 0 deep enrichment (fail-safe).
-   spec: Document lookup default and bump specification version to
    1.0.70.

## 2026-02-14T22:00:00+01:00

-   Issue 508: import_wizard: Unify PHASE 0 and PHASE 2 identity
    fingerprint builder (stat-based) and remove full-file hashing from
    processing.

## 2026-02-14T21:30:00+01:00

-   Issue 507: import_wizard: Export book fingerprint identity key and
    rename_preview in the index API for the start screen.
-   spec: Document index books\[\] fingerprint/rename_preview fields and
    bump specification version to 1.0.69.

## 2026-02-14T18:10:00+01:00

-   web_interface: Add Import Wizard visual editor for PHASE 1 config
    (conflict policy + audio toggles) and persist per-mode defaults.
-   import: Add WizardDefaultsStore (JOBS root) to persist wizard
    defaults per wizard+mode and expose import_wizard defaults API
    endpoints.
-   spec: Document Import Wizard defaults memory and bump specification
    version to 1.0.68.
-   web_interface: Import Wizard processed_registry API returns keys for
    UI compatibility (legacy items/count retained).

## 2026-02-14T17:50:25+01:00

-   import_wizard: Add PHASE 1 Loudness/Bitrate step options with
    explicit confirmation and default bitrate 96 kbps.
-   import: Apply optional MP3 re-encode/loudnorm during PHASE 2 only
    when confirmed in PHASE 1.
-   spec: Document Issue 504 audio processing decisions and bump
    specification version to 1.0.66.

## 2026-02-14T17:20:00+01:00

-   import_cli: Extend interactive CLI import wizard to continue after
    book selection and collect PHASE 1 decisions before starting
    processing.

-   spec: Document CLI import wizard continuation and bump specification
    version to 1.0.64. \## 2026-02-14T14:52:20+01:00

-   web_interface: In debug mode, surface non-2xx HTTP responses as
    client-side debug records in the Logs UI, including response body
    (truncated) and callsite stack.

-   web_interface: In debug mode, show an immediate toast/modal for
    non-2xx HTTP responses so conflicts are not hidden in DevTools.

-   spec: Document debug-mode UI transparency for HTTP failures and bump
    specification version to 1.0.63. \## 2026-02-14T10:38:00+01:00

-   web_interface: Add debug-only "Debug JS" page that shows in-session
    JS errors (window.onerror + unhandledrejection) with
    filter/pause/clear/export.

-   web_interface: Ensure global JS error handlers never overwrite the
    UI.

-   spec: Document debug-only Debug JS page and bump specification
    version to 1.0.62. \## 2026-02-14T09:00:00+01:00

-   web_interface: Fix Import Wizard UI runtime error (fpKeyForBook
    undefined) by using a global fingerprint-key helper.

-   import: Enforce Issue 503 mode contract in engine (stage
    parallelism=2, inplace parallelism=1) regardless of caller-provided
    run state.

-   spec: Clarify stage parallelism is enforced and bump specification
    version to 1.0.65. \## 2026-02-14T00:05:00+01:00

-   import: Enforce stage vs inplace mode contract (resume + parallelism
    defaults).

-   import_wizard: Default conflict policy is ask, but block PHASE 2 job
    creation until conflicts are resolved.

-   import: Allow optional delete_source after successful staging,
    guarded by fingerprint identity.

-   spec: Document stage/in-place mode contract and bump specification
    version to 1.0.61. \## 2026-02-13T22:45:00+01:00

-   Issue 502: import_wizard: Add processed registry integration keyed
    by book fingerprint (algo:value).

-   Issue 502: import: Mark processed only on successful PHASE 2
    completion and support unmark.

-   Issue 502: web_interface: Gray-out processed books, disable Start,
    and add Unmark action in Import Wizard UI. \##
    2026-02-13T21:15:00+01:00

-   import_wizard: Deep enrichment now includes deterministic ID3
    majority vote, APIC cover markers, stronger fingerprints, and
    deterministic rename preview ordering.

-   spec: Document deep enrichment requirements and bump specification
    version to 1.0.60. \## 2026-02-13T21:00:00+01:00

-   Issue 500: import_wizard: Add fast index endpoint for start screen
    (2-level scan, no deep reads) with deterministic root signature
    cache under file_io JOBS.

-   Issue 500: import_wizard: Add background deep enrichment runner
    (non-blocking) and enrichment_status endpoint.

-   Issue 500: web_interface: Update Import Wizard UI to use index +
    enrichment polling; keep start/import endpoints unchanged.

-   spec: Update Import Wizard UX/API contract to include index +
    enrichment_status. \## 2026-02-13T20:30:00+01:00

-   Issue 706: web_interface: Add LogBus SSE stream/tail endpoints and
    expose them in Logs UI (auto-scroll).

-   web_interface: Add Logs UI download action for the debug bundle
    endpoint.

-   spec: Document LogBus endpoints and Logs UI debug bundle action;
    bump specification version to 1.0.58. \## 2026-02-13T19:00:00+01:00

-   Issue 416: import: Support file-based book units (archives + single
    audio) in PHASE 2 jobs.

-   tests: Add unit coverage for import job file sources.

-   spec: Document file-based import units and bump specification
    version to 1.0.57. \## 2026-02-13T14:35:00+01:00

-   core.jobs: Emit operation.start/operation.end for jobs.update_state
    and jobs.fail with required summary fields.

-   spec: Document jobs.fail operation lifecycle events. \##
    2026-02-13T14:05:00+01:00

-   file_io: Avoid duplicate file_io.resolve envelopes by not
    re-wrapping resolve_abs_path; add file_io.move operation (alias of
    rename) with start/end diagnostics and Core logger summaries.

-   spec: Document file_io.move operation and de-dup resolve envelope
    behavior. \## 2026-02-13T14:00:00+01:00

-   Issue 703: import: Emit contracted step-level runtime diagnostics
    envelopes for import wizard steps
    (preflight/scan/select_source/finish), including duration, safe
    aggregate summaries, and short tracebacks on failures.

-   spec: Document Import observability events and bump specification
    version to 1.0.55. \## 2026-02-13T12:30:00+01:00

-   syslog: Persist system log to logging.system_log_path under file_io
    STAGE root; enforce STAGE root validation and clear errors for
    invalid paths.

-   web_interface: Make /api/debug/bundle zip contents deterministic
    (stable internal paths; timestamps only in manifest.json).

-   web_interface: Add API snapshot files (status/roots/wizards/jobs) to
    debug bundle.

-   spec: Document syslog single source of truth and deterministic debug
    bundle contract; bump specification version to 1.0.54. \##
    2026-02-13T12:20:00+01:00

-   core.jobs: Emit job lifecycle diagnostics events (create/get/list,
    state changes, failure reasons).

-   spec: Document mandatory job observability events; bump
    specification version to 1.0.54. \## 2026-02-13T12:15:00+01:00

-   Issue 701: file_io: Emit operation.start/operation.end runtime
    diagnostics (diagnostics.jsonl) and Core logger summaries for file
    operations, including resolver decisions (resolved_path), counts,
    delete status, and short tracebacks on failures. \##
    2026-02-13T12:00:00+01:00

-   Issue 333: web_interface: Emit operational logs via Core logger
    (LogBus) for request and handler operations; include traceback on
    failures.

-   Issue 333: web_interface: fs API uses FileService
    open_read/open_write (no read_bytes/write_bytes).

-   Issue 333: web_interface: logs API removes redundant UTF-8 encoding
    argument to satisfy linting. \## 2026-02-13T00:30:00+01:00

-   web_interface: Add "/api/debug/bundle" ZIP endpoint and Import page
    "Download debug info" action.

-   web_interface: Keep uvicorn access logs disabled (even in debug);
    rely on boundary diagnostics instead.

-   import_cli: Emit explicit preflight boundary diagnostics with
    duration and route DIAG envelopes through debug LogBus.

-   import: Emit per-job import job boundary diagnostics (duration_ms +
    traceback) from the engine service.

-   tests: Add integration coverage for import CLI diagnostics stdout
    and syslog persistence. \## 2026-02-13T00:15:00+01:00

-   web_interface: Import wizard preflight auto-load (debounced) and
    improved error detail rendering.

-   web_interface: Import wizard preflight includes synthetic
    "`<book-only>`{=html}" author group when author-less books exist.

-   web_interface: Fix import_wizard/start 500 by constructing
    PreflightResult correctly; add import_wizard/status endpoint.

-   tests: Add unit coverage for web import wizard preflight grouping
    and start validation.

-   spec: Document web import wizard auto-load, book-only group, status
    endpoint; bump specification version to 1.0.50. \##
    2026-02-13T00:00:00+01:00

-   import_cli: Fix silent exits during interactive selection and
    support mixed inbox layouts (author/book, book-only, file units).

-   import_cli: In debug verbosity, print import-related diagnostics
    envelopes to stdout.

-   tests: Add unit coverage for mixed layout import CLI selection.

-   spec: Document import CLI UX stability rules; bump specification
    version to 1.0.49. \## 2026-02-12T23:53:10+01:00

-   import: Extend PHASE 0 import preflight to support mixed inbox
    layouts (author/book directories, single-level book directories, and
    single-file units for archives/audio) without modifying the inbox.

-   import: Emit explicit skipped entries (with reason) and stable
    book_ref per discovered unit.

-   tests: Add unit coverage for mixed inbox discovery.

-   spec: Document mixed inbox preflight behavior and bump specification
    version to 1.0.48. \## 2026-02-12T22:42:28+01:00

-   cli: Add AM1-like `audiomason import` command implemented as a
    plugin-provided CLI command (import_cli).

-   tests: Add unit coverage for import CLI command registration and
    argument parsing.

-   spec: Document CLI import command and bump specification version to
    1.0.47. \## 2026-02-12T22:30:00+01:00

-   web_interface: Add visual wizard configuration editor (drag reorder,
    enable toggle, templates, defaults memory) with server-side
    validation.

-   web_interface: Add /api/wizards/validate safe-save endpoint and
    strict model validation.

-   tests: Add unit coverage for wizard validation and
    backward-compatible parsing.

-   spec: Document wizard visual configuration editor and bump
    specification version to 1.0.46. \## 2026-02-12T21:52:44+01:00

-   web_interface: Add dedicated Import Wizard UI (author -\> book
    guided flow) backed by import plugin services.

-   web_interface: Add import_wizard API endpoints
    (preflight/start/run_pending).

-   spec: Document web import wizard UX and bump specification version
    to 1.0.45. \## 2026-02-12T19:10:00+01:00

-   import: Add PHASE 2 import processing engine with persisted Jobs and
    CLI-safe service API.

-   tests: Add unit coverage for import engine stage determinism,
    inplace semantics, retry behavior, and service entry. \##
    2026-02-12T18:45:00+01:00

-   import: Add import foundation infrastructure (run state store,
    deterministic preflight, processed registry) under plugins/import/.

-   tests: Add unit coverage for import foundation persistence and
    determinism.

-   spec: Document import wizard foundation and bump specification
    version to 1.0.43. \## 2026-02-12T18:32:21+01:00

-   diagnostics_console: Fix diag --help/-h handling; add
    wait_status_repeat and --mode events\|log\|both.

-   tests: Add deterministic unit tests for diagnostics_console CLI.

-   spec: Bump specification version to 1.0.42; document diagnostics
    console modes. \## 2026-02-12T18:00:00+01:00

-   file_io: Add tail_bytes (byte-level tail read) for UI
    diagnostics/system log viewers.

-   tests: Add unit coverage for tail_bytes.

-   spec: Document file_io tail_bytes operation. \##
    2026-02-12T14:59:43+01:00

-   syslog: Add syslog LogBus persistence plugin (file_io CONFIG root)
    with CLI (status/cat/tail).

-   spec: Document syslog plugin configuration and behavior; bump
    specification version to 1.0.41. \## 2026-02-12T09:43:00+01:00

-   core: Add LogBus (publish/subscribe) for log streaming, mirroring
    the EventBus model.

-   core: Remove file-backed system log backend; core no longer writes
    any log files.

-   docs: Update system log specification: persistence is performed by
    external LogBus subscribers using File I/O roots.

-   file_io: Add open_append (append-only upload streaming) for
    byte-level log appends.

-   tests: Add unit coverage for open_append stream and
    FileService.open_append.

-   spec: Document file_io open_append and bump specification version to
    1.0.39. \## 2026-02-12T08:30:00+01:00

-   Add config keys logging.system_log_enabled and
    logging.system_log_path for human-readable system log file routing.

-   Apply system log file configuration in CLI bootstrap (fail-safe;
    never crash on file errors).

-   Add resolver unit tests for system log keys.

-   spec: Document system log keys and bump specification version to
    1.0.38. \## 2026-02-11T20:45:00+01:00

-   plugins: Add diagnostics_console plugin providing `audiomason diag`
    (tail/status/on/off) for runtime diagnostics JSONL sink.

-   tests: Add unit coverage for diag command help registration and
    basic behavior.

-   spec: Document diagnostics console command; bump specification
    version to 1.0.37. \## 2026-02-11T20:08:27+01:00

-   Normalized runtime diagnostic events to always publish the canonical
    envelope schema.

-   Added mandatory diagnostics event set
    (jobs/contexts/boundaries/pipelines/wizards) including boundary.fail
    and duration_ms.

-   Added pytest coverage for diagnostics envelope shape and minimal
    event sequences during pipeline execution. \##
    2026-02-11T18:23:13+01:00

-   core: Add EventBus.subscribe_all to support all-event subscribers.

-   core: Add runtime diagnostics envelope and JSONL sink
    (config/env/cli enablement).

-   CLI: Add --diagnostics/--no-diagnostics flags and always-register
    diagnostics sink.

-   tests: Add coverage for diagnostics sink enablement, wrapping,
    idempotency, and subscribe_all.

-   spec: Document runtime diagnostics envelope and JSONL sink; bump
    specification version to 1.0.35. \## 2026-02-11T17:41:11+01:00

-   spec: Document web wizard job payload source_path injection; bump
    specification version to 1.0.34. \## 2026-02-11T15:00:00+01:00

-   docs: Record core ruff-driven formatting fixes; enforce docs gate
    requirements.

-   spec: Bump specification version to 1.0.33.

-   web_interface: Stream and tail diagnostics/events via Core EventBus
    tap; emit API route boundary diagnostics; emit import action events
    (preflight/queue/run/pause/resume).

## 2026-02-16T07:00:00+01:00

-   Issue 600: Wizard platform migration --- remove legacy Core wizard
    runtime; wizard authority moved to Import plugin.

-   Docs: Update specification to v1.0.88 and document breaking change
    in changes log.

-   Wizard definitions remain at `wizards/definitions/*.yaml` under
    file_io root `wizards` (storage unchanged; runtime/authority
    updated). \## 2026-02-17T12:00:00+01:00

-   Issue 600: Remove legacy Core wizard runtime and all legacy UI
    surfaces (CLI `wizard`, TUI wizard actions, web_interface wizard
    endpoints).

-   web_interface: Keep mount_wizards import hook as a no-op to preserve
    plugin import graph.

-   tests: Remove unit coverage for legacy wizard orchestration; keep
    Jobs deterministic ordering coverage.

-   Issue 600: Remove remaining legacy wizard residues: remove
    `JobType.WIZARD` and remove `POST /api/jobs/wizard`.

-   tests: Remove remaining unit coverage for legacy wizard endpoints
    and wizard job creation.

-   spec: Clarify that wizard routing/command rules are conditional and
    bump specification version to 1.0.91.

## 2026-02-18T00:00:00+01:00

-   Issue 206: Import wizard flow now distinguishes required vs optional
    steps; FlowConfig may disable optional steps and the engine
    deterministically skips them during next/back transitions.

## 2026-02-18T00:00:00+01:00

-   Issue 207: Import wizard conflict policy is now applied to session
    state; resolve_conflicts_batch persists a resolution decision and
    unblocks processing when policy=ask.

-   Issue 207: start_processing(confirm=true) now transitions the
    session to PHASE 2 and locks interactive submit_step/apply_action;
    the terminal step_id processing is used when available.

## 2026-02-18T00:00:00+01:00

-   Issue 207: GET /import/ui/flow now returns runtime FlowModel (flow_id + steps[]) derived from FlowConfig.
-   Issue 207: final_summary_confirm now deterministically transitions to processing or resolve_conflicts_batch per spec; resolve_conflicts_batch OK returns to final_summary_confirm.

## 2026-02-18T00:00:00+01:00

-   Issue 210: import plugin now enforces atomic JSONL persistence for decisions.jsonl
    (rewrite + atomic rename) to satisfy spec 10.7.

-   Issue 210: ModelValidationError is now mapped to INVARIANT_VIOLATION (spec 10.6/10.4.1),
    and import UI routes consistently return canonical error envelopes.

-   spec: Bump specification version to 1.1.5 and document import storage artifacts
    (derived session files) and flow_config.json bootstrap requirements.

## 2026-02-19T00:00:00+01:00

-   Issue 213: Import wizard selection steps now provide deterministic author/book selectable items
    (item_id + ASCII label) in the per-session effective_model.json; CLI renderer lists schema items
    without import-specific step branching.

-   Issue 214: Import plan.json now includes selected_books derived from selected_book_ids; plan summary
    counts reflect the selected books; invalid/inconsistent selection during plan_preview_batch
    deterministically transitions back to select_books.

-   Issue 215: Conflict scanning now derives conflicts from plan.json planned target outputs
    and persists canonically ordered conflict items for deterministic re-check.

-   spec: Bump specification version to 1.1.11 and document plan-based conflict scanning.

-   Issue 216: job_requests.json now derives per-book actions from plan.json and start_processing
    returns batch_size equal to the number of planned units.

-   spec: Bump specification version to 1.1.12 and document plan-based job request batching.

-   Issue 218: Fix model_fingerprint to match the final persisted effective_model.json
    (post-enrichment), including the resume reinjection path.

-   spec: Bump specification version to 1.1.13 and clarify model_fingerprint is computed
    over the final persisted effective_model.json (after enrichment).

## 2026-02-20T00:00:00+01:00

-   Issue 223: POST /import/ui/config now supports a deterministic patch mode wrapper
    (mode=patch, ops=[{op:set,path,value}, ...]) applied atomically to the persisted
    FlowConfig with canonical error envelopes on validation failures.

-   Issue 224: Import wizard now enforces spec 10.2 three-phase rules: PHASE 1 never
    creates jobs; start_processing transitions to PHASE 2 before job creation; PHASE 2
    interactions are hard contract errors (invariant_violation).

## 2026-02-21T00:00:00+01:00

-   Issue 226: FlowConfig v1 normalization now rejects unknown top-level keys and omits conflicts.

-   Issue 226: Error JSON now enforces ASCII-only error.message for all envelopes (10.4.1).

-   Issue 226: Engine now validates baseline field definitions authoritatively before processing payloads (10.4.3).

-   spec: Bump specification version to 1.1.15 and clarify FlowConfig conflicts exclusion.

-   Issue 230: Import selection items now include display_label (Unicode) for renderer display,
    while keeping label ASCII-only for backward compatibility.

-   Issue 230: Import plan relative path fields now preserve exact Unicode paths (no ASCII replacement).

-   spec: Bump specification version to 1.1.17 and document display_label for selection items.

## 2026-02-23T00:00:00+01:00

-   Issue 237: Import UI session state now includes effective_model loaded from
    sessions/<session_id>/effective_model.json, and the Web UI renders steps and
    multi_select_indexed items from the session effective_model after session start.

-   spec: Bump specification version to 1.1.21.

## 2026-02-24T00:00:00+01:00

-   Issue 240: Import plugin Web UI now includes FlowConfig and WizardDefinition
    editors (tabs) with validate, save, reset, history, and rollback.

-   Issue 240: UI editor routes now enforce wrapper contracts and reject unknown
    root keys, returning canonical error envelopes.

-   spec: Bump specification version to 1.1.24.

## 2026-02-24T00:00:00+01:00
- spec: WizardDefinition v2 FlowGraph (branching nodes/edges)
- spec: Deterministic condition language for edges (no code)
- spec: Follow-up questions modeled as nodes/edges
- spec: Define step settings ownership via FlowConfig.defaults[step_id]
- spec: Bump specification version to 1.1.27

## 2026-02-26T00:00:00+01:00

-   Issue 264: Consolidate Flow Editor UI into a single grid layout (main + deterministic sidebar sections).

-   Issue 264: Introduce event-based UI state updates so config edits do not rebuild the wizard table.

-   Issue 264: Enforce step behavioral metadata fields and validate FlowGraph invariants before job creation.

-   spec: Bump specification version to 1.1.29.

-   Issue 265: Remove raw JSON condition editing from Transitions; add a visual condition builder
    with server-defined path prefixes.

-   Issue 265: Step Details now renders behavioral summary, input contract, output contract,
    and side effects description.

-   Issue 265: Step Palette now shows displayName and shortDescription; toolbar Add Step only
    focuses the palette (no implicit insertion).

-   Issue 265: Unified mode config editor no longer mirrors cfgJson on each field mutation;
    JSON text is refreshed only on reload/validate/save.

-   Issue 265: Save All gating is centralized on FlowEditorState validation_changed,
    wizard_changed, and config_changed, enabling Save only when lastOk=true and draftDirty=false.

-   spec: Bump specification version to 1.1.30.

-   Issue 301: Flow Editor sidebar no longer duplicates Transitions/Palette titles;
    Step Details renders read-only step metadata from /import/ui/steps/{step_id}.

-   spec: Bump specification version to 1.1.32.

-   Issue 400: Flow Editor Step Details is now editable via FlowConfig draft; added
    window.AM2FlowConfigEditor.renderNow() and sidebar-friendly UX text; added Activate.

-   spec: Bump specification version to 1.1.33.

-   Issue 401: Flow Editor Step Details no longer overwritten by read-only renderer; Step Details panel is owned by FlowConfig editor.

-   spec: Bump specification version to 1.1.34.

-   Issue 24: PatchHub /debug page will expose per-section Flush and Copy actions for debug feeds.

-   spec: Bump specification version to 1.1.35.

-   Issue 117: WizardDefinition draft reset now seeds from the active definition, stale draft shadowing is quarantined, and stale activate no longer downgrades active runtime.
