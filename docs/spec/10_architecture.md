# AudioMason2 - Architecture Specification (Authoritative)

Specification Version: 1.1.26
This document contains the ARCH layer of the AudioMason2 specification.
It defines architectural invariants and contracts without wire-level
HTTP/JSON details and without file-layout bindings.

------------------------------------------------------------------------

# AudioMason2 - Project Specification (Authoritative)

Specification Version: 1.1.22 Specification Versioning Policy: Start at
1.0.0. Patch version increments by +1 for every change.

Author: Michal Holes\
Status: **AUTHORITATIVE / BINDING**\
Applies to: AudioMason2 core, plugins, tooling, UI, tests,
documentation\
Language: **English (mandatory for all repository content)**

------------------------------------------------------------------------

## 1. Purpose of This Document

This document is the **authoritative specification** for the AudioMason2
(AM2) project.

Its role is to:

-   define **what AudioMason2 is and must be**,
-   establish **non?negotiable architectural and behavioral rules**,
-   act as a **binding contract** for all future development,
-   prevent architectural drift, monolith growth, and ad?hoc fixes,
-   ensure long?term maintainability, testability, and extensibility.

Any implementation, patch, refactor, or feature **must comply with this
specification**.

If a change contradicts this document, the change is **invalid** unless
the specification itself is updated and approved first.

------------------------------------------------------------------------

## Specification Versioning and Change Log

This specification is versioned. The version is tracked near the top of
this document.

Rules:

-   Start at version 1.0.0.
-   Every change to this specification MUST increment the patch number
    by +1 (e.g. 1.0.0 -\> 1.0.1).
-   Every change delivered by a patch MUST be recorded in
    docs/changes.md.
-   Each change entry in docs/changes.md MUST start with an ISO 8601
    timestamp captured at patch creation time.

### docs/changes.md - Canonical Change Log Format (MANDATORY)

The file docs/changes.md is a **pure chronological change log**.

It MUST contain: - only ISO 8601 timestamps and human-readable
descriptions of changes, - entries ordered strictly by time (newest
first or oldest first, but consistent), - one or more change
descriptions per timestamp.

It MUST NOT contain: - issue numbers or issue references, - issue
groupings or headings (e.g. "Issue 123"), - patch IDs, commit hashes, or
author names, - explanations of motivation, discussion, or process.

docs/changes.md records **what changed and when**, nothing else. Process
tracking (issues, discussions, rationale) belongs elsewhere.

## 2. Core Vision

AudioMason2 is a **general?purpose, plugin?driven, asynchronous media
processing platform** with a strong focus on:

-   audiobooks (primary use case),
-   deterministic behavior,
-   user?controlled workflows,
-   extensibility through plugins,
-   multiple user interfaces (CLI, Web, Daemon),
-   long?term evolvability without rewrites.

AM2 is not a collection of scripts.\
AM2 is an **engine + ecosystem**.

------------------------------------------------------------------------

## 3. Fundamental Principles (Non?Negotiable)

### 3.1 Ultra?Minimal Core

-   Core contains **infrastructure only**, never business logic.
-   Core must remain small, readable, and stable.
-   Core responsibilities:
    -   plugin loading and orchestration
    -   configuration resolution
    -   job orchestration
    -   pipeline execution infrastructure
    -   error and phase enforcement

Core must **never**: - implement audio processing - implement metadata
fetching - implement UI logic - implement storage backends

Everything else is a plugin.

------------------------------------------------------------------------

### 3.2 Plugin?First Architecture

-   Plugins are the primary extension mechanism.
-   Core depends on **interfaces**, never concrete implementations.
-   Plugins may add, modify, or disable behavior.
-   Plugins must be isolatable and removable without breaking the
    system.

No feature may be added directly to core if it can exist as a plugin.

------------------------------------------------------------------------

### 3.3 Deterministic Behavior

-   Same inputs + same config = same outputs.
-   No hidden state.
-   No time?dependent logic unless explicitly modeled.
-   All behavior must be observable via logs and job state.

------------------------------------------------------------------------

### 3.4 Asynchronous by Design

-   Long?running operations must be asynchronous.
-   UI must never block on processing.
-   Progress and logs must be observable while work is running.

Synchronous shortcuts are forbidden except for trivial operations.

------------------------------------------------------------------------

## 4. Execution Model (Strict Contract)

### 4.1 Three-phase Model

All processing follows **exactly** these phases:

1.  **PHASE 0 - Preflight**
    -   Detection
    -   No user interaction
2.  **PHASE 1 - User Input**
    -   Interactive
    -   UI=controlled (CLI/Web)
    -   All decisions are collected here
3.  **PHASE 2 - Processing**
    -   **STRICTLY NON-INTERACTIVE**
    -   Async background execution
    -   No prompts, no questions, no UI calls

Violation of phase boundaries is a **hard error**.

------------------------------------------------------------------------

### 4.2 Phase Enforcement

-   Phase rules are enforced centrally in core.
-   Any attempt to interact with the user during PHASE 2 must:
    -   raise a contract violation error,
    -   fail the job deterministically,
    -   preserve partial results and checkpoints if possible.

------------------------------------------------------------------------

## 5. Job Model (Mandatory)

### 5.1 Jobs as the Only Execution Unit

-   Every operation that does work is a **Job**.
-   UI layers may only:
    -   create jobs
    -   observe jobs
    -   cancel jobs

UI layers may **never** execute pipelines directly.

------------------------------------------------------------------------

### 5.2 Job Properties

Each job has at minimum:

-   unique job_id
-   type (process, wizard, daemon, etc.)
-   state (PENDING, RUNNING, SUCCEEDED, FAILED, CANCELLED)
-   progress (0.0-1.0)
-   timestamps
-   bound log stream

------------------------------------------------------------------------

### 5.3 Job Persistence

-   Jobs must be persisted.
-   Storage backend is abstracted and replaceable.
-   Loss of job state after restart is unacceptable.

### 5.4 Job Observability (Mandatory)

Jobs MUST emit lifecycle diagnostics through the authoritative EventBus.

Minimum events:

-   operation.start / operation.end with operation one of: jobs.create,
    jobs.get, jobs.list, jobs.update_state
-   operation.start / operation.end with operation one of: jobs.fail
-   jobs.create, jobs.get, jobs.list
-   jobs.update_state on state or progress changes
-   jobs.fail when a job fails, including error_type, error_message, and
    a shortened traceback if available

Events MUST include at minimum: - job_id - job_type - state - progress
(when available) - status - duration_ms (for operation.\* events)

-   Jobs must be persisted.
-   Storage backend is abstracted and replaceable.
-   Loss of job state after restart is unacceptable.

------------------------------------------------------------------------

## 6. Configuration System

### 6.1 Single Access Path

-   All runtime configuration access goes through **ConfigResolver
    API**.
-   No component may read configuration files directly.

------------------------------------------------------------------------

### 6.2 Priority Rules

Configuration priority is fixed and mandatory:

1.  CLI arguments\
2.  Environment variables\
3.  User configuration\
4.  System configuration\
5.  Defaults

The source of each resolved value must be traceable in debug mode.

------------------------------------------------------------------------

### 6.3 Configuration Schema Registry

-   ConfigResolver must expose an authoritative schema registry for
    known configuration keys.
-   Each schema entry must define at minimum:
    -   key_path (dot notation, e.g. "web.port")
    -   value_type ("string" \| "int" \| "bool" \| "enum" \| "list" \|
        "object" \| "path")
    -   description (ASCII-only)
    -   default (if defined)
    -   enum_values (only for enum)

UI and other layers consume the schema through resolver APIs. UI is
never a source of truth.

------------------------------------------------------------------------

### 6.4 Deterministic Key Enumeration

-   Resolver must provide a deterministic list of known keys:
    -   `list_known_keys() -> list[str]` returns schema keys sorted
        lexicographically.
-   `resolve_all()` must enumerate at least all known keys from the
    schema.

------------------------------------------------------------------------

### 6.5 Unknown Keys Policy (Compatibility)

-   Unknown keys (keys not present in the schema registry) are permitted
    for compatibility.
-   Unknown keys are treated as type `any`:
    -   no type validation is applied by resolver
    -   admin tooling may surface them as "unknown/advanced"
-   Unknown keys must not make the resolver non-deterministic.

------------------------------------------------------------------------

### 6.6 Minimal Type Validation (Known Keys)

-   Known keys (present in schema) must support minimal type validation:
    -   int: must be int (no implicit string coercion unless schema
        explicitly allows it)
    -   bool: must be bool (no implicit string coercion unless schema
        explicitly allows it)
    -   enum: must be one of the allowed enum values
    -   path: baseline is string (no filesystem checks in this baseline)

------------------------------------------------------------------------

### 6.7 Canonical Logging Verbosity

Canonical key: - `logging.level`

Allowed values (after normalization): - `quiet` - `normal` - `verbose` -
`debug`

### 6.7.A Console Output Policy (Normative)

In canonical logging level `normal`, the interactive CLI launcher
(`audiomason import`) MUST NOT emit high-volume internal INFO logs from
underlying services/plugins to the interactive console UI output.

Such logs MUST remain available via LogBus.

They MAY be emitted only in `verbose` or `debug`.

Warnings and errors MUST remain visible in `normal`.

### 6.7.1 Human-Readable System Log File

Core does not implement a file-backed system log backend. Instead, Core
emits a human-readable log stream via a Core-owned publish/subscribe bus
called LogBus.

Semantics: - Every log line emitted by the Core logger is published to
LogBus as a LogRecord (plain, no colors, no trailing newline). - If no
subscribers exist, publishing is a no-op (logs are effectively
dropped). - If a subscriber raises, the exception is suppressed and
reported to stderr; the system must not crash.

Persistence semantics: - Log persistence is performed by external
subscribers (plugins) that subscribe to LogBus. - Persistence MUST use
the File I/O capability (and its roots). UI layers must not write to
arbitrary filesystem paths directly. - If no persistence subscriber
exists, no human-readable system log file is created or updated.

Diagnostics note: - LogBus is a log streaming mechanism only. It is NOT
the authoritative runtime diagnostic emission entry point. Diagnostic
lifecycle events remain exclusively emitted via the existing Core
diagnostic entry point as specified elsewhere in this document and in
the base project contract.

------------------------------------------------------------------------

### 6.7.2 Syslog plugin

The syslog plugin is a LogBus subscriber that persists Core log records
to a file under the file_io STAGE root. Core remains independent of this
plugin.

Behavior: - Subscribes to LogBus only when enabled. - Persists records
via file_io (no direct filesystem access in the plugin). - Append-only
file semantics.

Configuration (single source of truth): - logging.system_log_enabled:
bool (default false) - logging.system_log_path: string (path under STAGE
root)

The plugin MUST validate that logging.system_log_path resolves under the
file_io STAGE root and fail with a clear error if the path is invalid.

Deprecated: - plugins.syslog.filename (must not be used anymore)

### 6.8 ConfigService Mutation Primitives

UI layers must not edit raw YAML directly. If a UI needs to mutate user
configuration, it must use ConfigService.

ConfigService provides two execution primitives:

-   `set_value(key_path, value)`
    -   writes a single key path into the user config YAML
    -   unknown keys are allowed and are not validated
    -   minimal validation is applied only for `logging.level`
        (quiet\|normal\|verbose\|debug)
-   `unset_value(key_path)`
    -   removes a single key path from the user config YAML (reset to
        inherit)
    -   prunes empty parent mappings recursively
    -   idempotent: unsetting a missing key is a no-op

ConfigService must re-initialize the resolver after each mutation so
subsequent reads reflect the change deterministically.

Normalization rules: - value must be a string - trim whitespace -
lowercase - empty string is invalid

Default semantics: - If no source provides `logging.level`, resolver
returns `normal`.

Failure semantics: - Resolver raises ConfigError if value is non-string,
empty/whitespace, or not in the allowed set.

------------------------------------------------------------------------

### 6.4 Resolved LoggingPolicy

The configuration resolver MUST provide a canonical, structured logging
policy derived from the canonical verbosity key. This ensures that the
meaning of verbosity is defined in exactly one place.

Type: LoggingPolicy (immutable)

Fields: - level_name: str - One of: quiet \| normal \| verbose \|
debug - emit_error: bool - emit_warning: bool - emit_info: bool -
emit_progress: bool - emit_debug: bool - sources: dict\[str,
ConfigSource\] - Must include the source for level_name under the key
"level_name".

Semantics (derived deterministically from level_name):

quiet: - emit_error = True - emit_warning = True - emit_info = False -
emit_progress = False - emit_debug = False

normal: - emit_error = True - emit_warning = True - emit_info = True -
emit_progress = True - emit_debug = False

verbose: - emit_error = True - emit_warning = True - emit_info = True -
emit_progress = True - emit_debug = False

debug: - Same as verbose, except: - emit_debug = True

Alias rules (resolver-only): - The legacy key "verbosity" is treated as
an alias for "logging.level". - If both are present, "logging.level"
ALWAYS wins. - Consumers MUST NOT be aware of aliases.

CLI input rules: - CLI MUST set the canonical key logging.level (nested:
logging.level). - CLI MUST NOT set the resolver-only alias verbosity.

Guarantees: - resolve_logging_policy() is deterministic and side-effect
free. - No numeric levels and no coupling to any logging library.

------------------------------------------------------------------------

## 7. Plugin System Specification

### 7.1 Plugin Registry

-   There must be a single **PluginRegistry API**.
-   It is the only source of truth for:
    -   discovery
    -   enable/disable state
    -   plugin configuration stored in host config under the canonical
        key-space
    -   metadata

Multiple parallel plugin state mechanisms are forbidden.

#### 7.1.1 Canonical plugin configuration key-space (host config)

Plugin configuration is host configuration and MUST be stored under:

-   plugins.`<plugin_id>`{=html}.config.`<key>`{=html}

#### 7.1.2 Plugin config default normalization (deterministic)

During plugin load, the host performs an explicit normalization step:

-   Inputs:
    -   plugin_id
    -   plugin manifest config_schema
-   Behavior:
    -   For each schema key missing under
        plugins.`<plugin_id>`{=html}.config:
        -   If the schema entry defines a default value (field
            "default"), write that default.
    -   Existing user values are never overwritten.
    -   If no keys are missing, no write occurs.
    -   Deterministic iteration order: lexicographic by schema key.
-   Storage:
    -   All writes go through ConfigService (no direct YAML access).

#### 7.1.3 Obsolete plugins.yaml

The legacy file "\~/.config/audiomason/plugins.yaml" is
obsolete/unsupported and MUST NOT be used for plugin state or plugin
configuration.

------------------------------------------------------------------------

### 7.2 Plugin Isolation

-   Plugin failure must not crash the system.
-   A failed plugin may be skipped with a warning.
-   Plugins must not assume filesystem layout or config storage.

------------------------------------------------------------------------

### 7.3 Plugin Installation Rules

-   Runtime mutation of repository plugins is forbidden.
-   User?installed plugins live in user plugin directories only.
-   Installation mechanism must be abstracted.

### 7.3.1 Built-in Plugin Import Path Rules (Loader Responsibility)

-   Built-in plugin loading MUST work without requiring the user to set
    PYTHONPATH.
-   When loading built-in plugins from the repository 'plugins/'
    package, the core plugin loader MUST ensure the repository root is
    present on sys.path so that absolute imports like 'plugins.\*' are
    resolvable.
-   This rule applies only to built-in plugins. Loading plugins from
    user/system plugin directories MUST NOT implicitly grant
    repository-root import privileges.

### 7.4 File I/O Capability (Plugin-Owned)

-   File operations are provided by the `file_io` plugin as a reusable
    capability.
-   UI layers (CLI, Web, TUI) must not implement filesystem logic; they
    call this capability.
-   Core must not implement a storage backend; file I/O remains
    plugin-owned.

#### 7.4.1 Roots

The file I/O capability must support named roots:

-   inbox: input drop area for new sources
-   stage: general staging area (non-job-specific)
-   jobs: isolated per-job workspaces
-   outbox: outputs intended for download/export
-   config: configuration-owned filesystem data (optional)
-   wizards: wizard-owned filesystem data

#### 7.4.2 Operations

The capability must provide, at minimum:

-   list_dir (stable deterministic order)
-   stat
-   exists
-   open_read (download streaming)
-   tail_bytes (download tail primitive)
-   open_write (upload streaming)
-   open_append (upload streaming append-only)
-   mkdir (parents supported)
-   rename (move)
-   delete_file
-   rmdir (empty directories only)
-   rmtree (recursive delete)
-   copy
-   checksum (sha256 default)

Append rules:

-   Append is a byte-level primitive (callers provide bytes; no
    formatting).
-   The file I/O capability must not implement rotation, size limits, or
    flush policy.

Tail rules:

-   tail_bytes is a byte-level primitive (callers interpret bytes; no
    decoding).
-   The file I/O capability must not implement follow, rotation,
    formatting, or line parsing.

#### 7.4.3 Determinism Rules

-   list_dir ordering must be stable and deterministic (lexicographic by
    relative path).
-   checksum must be deterministic (sha256 over file bytes).
-   The file service itself must not generate random or time-based
    names.

#### 7.4.4 Separation From Pipeline Semantics

-   Pipeline steps (import/export/extract/preflight) may use the file
    capability.
-   Naming policy and cleanup policy are part of pipeline behavior, not
    the core file capability.

#### 7.4.5 Archive Capability (Plugin-Owned)

The file I/O plugin must provide an archive capability built on top of
the file roots.

This capability must support:

-   pack: create an archive from a directory under a root
-   unpack: extract an archive under a root into a destination directory
    under a root
-   plan_pack and plan_unpack: return a deterministic plan without
    executing changes
-   detect_format: optional helper, executed only when explicitly
    requested by higher layers

Required behavior:

-   The higher layer must be able to specify the exact archive filename
    to create.
-   The higher layer must be able to specify the destination directory
    name to unpack into.
-   The higher layer must be able to choose:
    -   preserve_tree: keep the directory structure inside the archive
    -   flatten: extract all files into a single directory
-   When flattening, the higher layer must be able to select a collision
    policy:
    -   error: fail on name collisions
    -   rename: deterministically rename collisions with \_\_N suffixes
    -   overwrite: overwrite existing destination files

Format support:

-   ZIP (pack and unpack, deterministic pack)
-   TAR, TAR.GZ, TAR.XZ (pack and unpack, deterministic pack)
-   RAR (unpack is required; pack is best-effort and may depend on
    external tools)

Determinism note:

-   Deterministic pack output is guaranteed for the stdlib ZIP/TAR
    backends.
-   RAR pack may not be deterministic across tools/versions and is
    best-effort.

Debug/trace support:

-   The archive capability must be able to emit a structured operation
    trace, including planned and ok/error phases, when explicitly
    enabled by configuration or request parameters.

------------------------------------------------------------------------

------------------------------------------------------------------------

### 7.5 CLI Plugin Command Extension

Note: The built-in CLI host is implemented as a plugin with manifest
name `cmd_interface`.

This section defines the contract for extending the AudioMason2 CLI with
plugin-provided commands.

This mechanism is strictly limited to adding new CLI commands. Plugins
MUST NOT modify, override, intercept, or disable existing CLI commands.

This section intentionally defines stricter constraints for CLI
extensibility than the general plugin capability model described
elsewhere in this specification.

#### 7.5.1 Ownership and Responsibility

-   CLI command extensibility is owned by the CLI plugin.
-   Core MUST NOT provide a global CLI hook bus.
-   Core responsibilities end at plugin discovery, manifest loading, and
    enable/disable state via PluginRegistry.

#### 7.5.2 Declaration Contract

Plugins that provide CLI commands MUST explicitly declare this
capability via a dedicated interface.

-   The canonical interface name is: ICLICommands
-   Plugins that do not declare this interface MUST be ignored for CLI
    command registration.
-   Implicit or heuristic detection is forbidden.

#### 7.5.3 Discovery Sources

The CLI plugin MAY discover CLI command providers from all supported
plugin sources:

-   built-in plugins
-   user plugins
-   system plugins

Discovery MUST be deterministic and independent of filesystem
enumeration order.

#### 7.5.4 Loading Model

A hybrid loading model is required:

-   At CLI startup, the system MUST perform lightweight discovery
    (manifest reads, validation, and command stub preparation).
-   Full plugin import and initialization MUST NOT occur until the
    corresponding CLI command is invoked.
-   Manifest-only discovery MUST NOT execute plugin code.

#### 7.5.5 Command Name Rules

Plugin-provided CLI command names MUST be globally unique.

-   Command name collisions are FORBIDDEN.
-   Any collision MUST result in a deterministic error.
-   Silent overrides or filesystem-order resolution are prohibited.

#### 7.5.6 Failure Isolation

Failure of a CLI command plugin MUST NOT crash the CLI.

-   A plugin that fails during loading or execution MUST be disabled for
    the current session.
-   Other CLI commands MUST remain available.
-   Errors SHOULD be reported clearly to the user.

#### 7.5.7 Enable / Disable Semantics

CLI command registration MUST respect PluginRegistry.

-   Disabled plugins MUST NOT register CLI commands.
-   Plugin enable/disable state is authoritative and centralized.

#### 7.5.8 User Visibility

The origin of every plugin-provided CLI command MUST be visible to the
user.

-   Help output MUST indicate the providing plugin for each
    plugin-provided command.
-   Anonymous or hidden command registration is forbidden.

#### 7.5.9 Determinism Requirements

All CLI plugin command behavior MUST be deterministic.

-   Plugin processing order MUST be explicitly defined and stable.
-   Filesystem order MUST NOT affect behavior.
-   Help output, command lists, and error messages SHOULD be stable
    across runs.

### 7.5.10 ICLICommands Interface Contract

Plugins that declare the `ICLICommands` interface MUST implement the
following Python-level contract.

The plugin class MUST expose a method:

`get_cli_commands() -> dict[str, Callable]`

Normative requirements:

-   Dictionary keys MUST be CLI command names.
-   Command names MUST:
    -   be lowercase,
    -   contain only ASCII letters, digits, and hyphens,
    -   not conflict with existing core CLI commands.
-   Dictionary values MUST be callables.
-   Callables MUST accept a single argument: `argv: list[str]`.
-   Callables MAY be synchronous or asynchronous.
-   The CLI host MUST transparently support both sync and async
    handlers.
-   The CLI host MUST NOT call `get_cli_commands()` until the command is
    invoked.

### 7.5.11 Deterministic Discovery and Ordering Rules

All CLI command plugin discovery MUST be deterministic.

Mandatory rules:

1.  Plugin discovery directories MUST be processed in this order:

    1.  built-in plugins
    2.  user plugins
    3.  system plugins

    The CLI host MUST preserve this source ordering when iterating
    discovered plugin directories. The CLI host MUST NOT globally
    re-sort the combined discovered list across sources.

2.  Within each directory:

    -   plugin directories MUST be sorted lexicographically by directory
        name.
    -   Sorting key MUST be the directory name (Path.name).

3.  For command registration:

    -   plugins MUST be ordered by `manifest.name` (lexicographically).
    -   filesystem iteration order MUST NOT influence behavior.

4.  If two plugins declare the same CLI command name:

    -   this is a fatal configuration error,
    -   the CLI MUST abort startup with a clear error message.

### 7.5.12 CLI Command Stub Registry

The CLI plugin MUST maintain an internal registry of CLI command stubs.

A command stub MUST contain: - command name, - providing plugin
identifier (`manifest.name`), - a reference sufficient to lazily load
the plugin.

Manifest requirement (Phase 2):

-   For plugins that declare `ICLICommands`, the plugin manifest
    (`plugin.yaml`) MUST declare the command names under
    `cli_commands: [<command-name>, ...]`.
-   This list MUST be used to build the stub registry and help output
    without importing plugin code.
-   If `ICLICommands` is not declared, `cli_commands` MUST be ignored.

At CLI startup: - only stubs MAY be registered, - plugin code MUST NOT
be imported.

On command invocation: - the CLI MUST load exactly one plugin, - call
`get_cli_commands()`, - resolve the requested command, - execute its
handler.

Phase 3 implementation requirement: - The built-in CLI plugin MUST
execute plugin-provided CLI commands by following this contract.

### 7.5.13 Failure Semantics for Command Invocation

If a CLI command plugin fails during load or execution:

-   the failure MUST NOT crash the CLI process,
-   the plugin MUST be marked as failed for the current session,
-   subsequent invocations MUST be rejected with a clear error,
-   other CLI commands MUST remain functional.

Failure of one plugin MUST NOT affect discovery or execution of other
plugins.

### 7.5.14 Help and User-Facing Output Format

The CLI help output MUST distinguish core commands from plugin commands.

For plugin-provided commands, the following format is mandatory:

`<command-name>    (plugin: <plugin-name>)`

The ordering of help output MUST be deterministic and stable across
runs.

If a plugin command exists but its plugin failed to load: - the command
MUST still appear in help output, - and MUST be annotated as
unavailable.

### 7.5.15 Relationship to Core CLI Dispatch

Core CLI commands take precedence in name resolution.

Resolution order: 1. Core CLI commands 2. Plugin-provided CLI commands

Plugins MUST NOT override or shadow core commands.

Reserved core command names (plugins MUST NOT provide these names): -
process - web - daemon - checkpoints - version - help

### 7.5.16 Reference Plugin: test_all_plugin

The repository includes a builtin reference plugin named
`test_all_plugin`.

Purpose:

-   Provide a canonical, deterministic "kitchen sink" example for plugin
    authors.
-   Provide stable integration test coverage for the plugin loader and
    CLI command extension.

Location:

-   `plugins/test_all_plugin/`

------------------------------------------------------------------------

## 10.1 Identity and Scope

-   Provided by plugin with manifest.name == "import".
-   Implements PHASE 0 (preflight/discovery) and PHASE 1 (interactive
    wizard engine).
-   Produces PHASE 2 job requests only; it MUST NOT execute PHASE 2
    processing directly.
-   UI layers (CLI/Web) are renderers only:
    -   They render steps, collect inputs, submit payloads.
    -   They MUST NOT implement validation, transitions, conflict
        scanning, job request generation, or any import-specific
        business logic.
-   The system MUST remain functional if the import plugin is disabled
    or absent.

## 10.2 Three-Phase Enforcement (Import Wizard)

The wizard MUST follow the global three-phase model:

-   PHASE 0: Preflight / discovery
    -   No user interaction.
    -   No jobs are created.
    -   No mutation of processed registry.
-   PHASE 1: User input
    -   Interactive steps only.
    -   No job creation.
    -   No processing execution.
-   PHASE 2: Processing
    -   STRICTLY non-interactive.
    -   Create jobs from canonical job_requests.json only.
    -   No prompts, no questions, no UI calls.

Any violation is a hard contract error.

## 10.3 Authoritative State Machine (Steps and Transitions)

### 10.3.1 Workflow Authority (WizardDefinition)

The wizard state machine (step set and transition graph) is defined by
the effective workflow snapshot generated at session creation time.

Source artifacts: - WizardDefinition (structural workflow):
`<wizards_root>`{=html}/import/definitions/wizard_definition.json -
FlowConfig (non-structural tuning only):
`<wizards_root>`{=html}/import/config/flow_config.json

At session creation, the engine MUST generate and persist the effective
workflow snapshot into: -
sessions/`<session_id>`{=html}/effective_model.json

This effective snapshot is the single source of truth for the active
session.

### 10.3.2 Mandatory Steps and Ordering Constraints

WizardDefinition MAY add, remove, reorder, or insert steps, but the
engine MUST enforce mandatory constraints to preserve phases and safety
invariants.

Mandatory step_ids (MUST exist in every effective workflow): S0
select_authors S1 select_books S2 plan_preview_batch (computed-only) S10
conflict_policy S12 final_summary_confirm S14 processing (PHASE 2
terminal)

Mandatory ordering constraints (MUST hold): - select_authors precedes
select_books. - select_books precedes plan_preview_batch. -
plan_preview_batch precedes conflict_policy. - conflict_policy precedes
final_summary_confirm. - final_summary_confirm precedes processing. -
processing is the only PHASE 2 terminal step.

Optional steps MAY be inserted between mandatory steps, subject to
Engine Guards (10.6) and phase rules.

### 10.3.3 Default Workflow

The default workflow provided by the system SHALL remain strictly linear
and equivalent to the previous canonical order, but it is now expressed
as the default WizardDefinition rather than as a hardcoded list. \###
10.3.3 Deterministic Error Behavior (ERR/OK)

-   ERR(payload): state MUST NOT advance; the current_step_id remains
    unchanged.
-   OK(payload): state MUST advance deterministically to the next step
    (or next enabled step).

Special rule: plan_preview_batch error handling MUST be deterministic: -
If plan_preview_batch fails due to invalid or inconsistent selection,
the engine MUST transition back to select_books.

### 10.3.4 Conditional Conflict Path

In final_summary_confirm:

-   If confirm_start == false:
    -   The state MUST remain final_summary_confirm (user must set true
        to proceed).
-   If confirm_start == true AND conflict_mode != "ask":
    -   Transition to processing.
-   If confirm_start == true AND conflict_mode == "ask":
    -   Engine MUST perform a conflict scan.
    -   If conflicts exist: transition to resolve_conflicts_batch.
    -   If no conflicts: transition to processing.

In resolve_conflicts_batch: - ERR: remain resolve_conflicts_batch. - OK:
transition back to final_summary_confirm.

### 10.3.5 Renderer Neutrality (Hard Rule)

Renderers (CLI/Web) MUST NOT contain import-specific branching logic
such as "if step_id == ...". All step behavior (validation, transitions,
conditional branching) MUST live in the wizard engine.

### 10.3.6 CLI Launcher and Renderer Configuration (Normative)

The CLI MAY provide an interactive renderer for the Import Wizard. This
is UI-only. It MUST delegate validation, transitions, conflict logic,
and job request generation to the engine.

Behavior: - The top-level command `audiomason import` is a CLI launcher
for the renderer. - Explicit subcommands `audiomason import wizard ...`
and `audiomason import editor ...` MUST remain supported and unchanged.

Configuration (read via ConfigResolver): -
`plugins.import.cli.launcher_mode`: one of `interactive` \| `fixed` \|
`disabled`. - `interactive` (default): `audiomason import` runs an
interactive renderer and MAY prompt for root/path. - `fixed`:
`audiomason import` runs the renderer without prompts using configured
defaults. - `disabled`: `audiomason import` MUST print usage (legacy
behavior) and MUST NOT start the renderer. -
`plugins.import.cli.default_root`: default RootName for session creation
(default: `inbox`). - `plugins.import.cli.default_path`: default
relative path under the selected root (default: empty string). -
`plugins.import.cli.noninteractive`: if true, the renderer MUST NOT
prompt and MUST fail if required inputs are missing. -
`plugins.import.cli.render.confirm_defaults`: if true, Enter MAY accept
defaults when prompting (default: true). -
`plugins.import.cli.render.show_internal_ids`: if true, the renderer MAY
display internal ids (default: false). -
`plugins.import.cli.render.max_list_items`: max items displayed in
interactive lists (default: 200). - `plugins.import.cli.render.nav_ui`:
navigation UI mode for interactive runs: - `prompt` (default): show
Action prompt after step submission - `inline`: do not show Action
prompt; accept `:back` and `:cancel` as inline commands - `both`: accept
inline commands and show Action prompt

CLI overrides: - The launcher MAY accept CLI flags that override the
resolver values for the current run. - Precedence MUST be: CLI flags \>
resolver config \> hard-coded defaults. - The launcher MUST provide a
way to force legacy usage output for a single run (e.g. `--no-launcher`
or `--launcher disabled`).

Root/path rules: - Root MUST be validated against RootName (file_io
roots). - Path MUST be a relative path and MUST NOT contain `..`. - Any
filesystem listing performed by the renderer MUST be done via
FileService and RootName (no direct filesystem access).

## 10.12 Config Governance (Editors and Storage)

If visual editors exist:

-   A Wizard editor modifies WizardDefinition only (structural
    workflow).
-   A Config editor modifies FlowConfig only (non-structural tuning).

Unified Flow Editor (Import plugin UI):

-   The UI MAY present the WizardDefinition editor and the FlowConfig editor in one screen.
-   The UI MUST maintain two independent drafts and persist them separately.
-   Structural edits (add/remove/reorder steps) MUST only affect WizardDefinition.
-   Step behavior/settings edits MUST only affect FlowConfig (for example: defaults[step_id]).
-   Validate All: the UI MUST validate both artifacts before allowing Save All.

Additional editor capabilities (if implemented):

-   A Step Schema editor modifies StepSchema only (field definitions and
    constraints).
-   A Provider editor modifies ProviderBindings only (provider
    selection, mapping, merge policy).

All editor-managed artifacts MUST implement a deterministic
Draft/Active/History lifecycle: - Draft state - Active state - History
snapshots (bounded retention = 5) - SHA-256 fingerprint identity over
canonical JSON bytes - Deterministic activation and rollback

Persisted artifacts MUST NOT include timestamps or editor metadata
fields.

Requirements: - Validate FlowConfig on load, save, import, and preset
apply. - Prevent saving invalid config (invariant violations). - Support
reset to built-in defaults. - If history/rollback is implemented: - keep
deterministic history with bounded retention N=5 (MANDATORY) - allow
deterministic rollback to a selected historic version - Defaults memory
(if implemented) MUST NOT update implicitly. - Only explicit user action
may update defaults. - Any auto-save (if implemented) MUST be visible
and reversible via history.

## 10.13 Performance and Scaling (Deterministic)

Performance rules are non-functional constraints but MUST NOT alter
outputs.

-   FlowModel build must be lightweight.
-   Selection parser must be linear time.
-   plan_preview_batch output MUST be bounded by preview_limit and MUST
    surface truncation explicitly.
-   conflict scan SHOULD be optimized with precomputed target path maps
    when feasible.
-   parallelism MUST be bounded by a hard MAX_PARALLELISM limit in the
    engine (implementation-defined but fixed).

Caches (if implemented): - cache keys MUST be deterministic - cache miss
MUST recompute (never silently fail) - enabling/disabling cache MUST NOT
change job_requests output

## 10.14 Diagnostics (Mandatory)

The import engine MUST emit via the Core authoritative diagnostic entry
point:

-   session.start
-   session.resume
-   model.load
-   model.validate
-   step.submit
-   plan.compute
-   finalize.request
-   job.create

Diagnostics MUST include at minimum: - session_id - model_fingerprint -
discovery_fingerprint - effective_config_fingerprint

## 10.15 Testing and Enforcement (Hard Gates)

The repository MUST include deterministic tests that enforce:

-   FlowBuilder invariants and mandatory step preservation.
-   Selection expression parser grammar and error behavior.
-   Session transitions: ERR does not advance; OK advances
    deterministically.
-   Conflict ask batch behavior (final_summary_confirm -\>
    resolve_conflicts_batch).
-   Phase enforcement (no jobs in PHASE 1; no step submits in PHASE 2).
-   Registry SUCCESS-only.
-   Canonical serialization stability (golden job_requests comparisons).
-   Renderer neutrality (static enforcement forbidding import-specific
    branching in UI layers).
-   Single source of truth for step ordering (BaseFlowDefinition defined
    exactly once).
-   Session snapshot isolation (config changes do not affect active
    sessions).
-   Conflict re-check before job creation.
-   Idempotency key enforcement (no duplicate jobs).

Integration completed (updated): 2026-02-18 06:00:00 UTC

------------------------------------------------------------------------

## 10.16 Structural Workflow Authority (WizardDefinition Model)

The Import Wizard structural workflow MUST be defined by a single
authoritative artifact named WizardDefinition.

Location (file_io root: wizards):

`<wizards_root>`{=html}/import/definitions/wizard_definition.json

Rules:

-   WizardDefinition defines structural workflow only:
    -   step ordering
    -   step types
    -   structural transitions
    -   action bindings
-   FlowConfig MUST NOT modify structure.
-   FlowConfig MAY modify only non-structural parameters (see 10.4.4).
-   WizardDefinition MUST be versioned and validated on load.
-   Structural edits affect only new sessions.

Active sessions MUST use a frozen effective_workflow snapshot.

------------------------------------------------------------------------

## 10.17 Interpreter Authority (Single Execution Engine)

The Import Wizard MUST use a single interpreter responsible for:

-   Step transitions
-   Validation
-   Conflict evaluation
-   Action execution
-   Job request generation

UI layers (CLI/Web) MUST:

-   Render step payload only
-   Submit user input
-   Never branch on step_id
-   Never execute plugin logic directly

Any UI-level business logic is a contract violation.

------------------------------------------------------------------------
