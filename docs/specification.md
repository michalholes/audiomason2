# AudioMason2 - Project Specification (Authoritative)

Specification Version: 1.1.16 Specification Versioning Policy: Start at
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
(`audiomason import`) MUST NOT emit high-volume internal INFO logs
from underlying services/plugins to the interactive console UI output.

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
    -   plugin configuration stored in host config under the canonical key-space
    -   metadata

Multiple parallel plugin state mechanisms are forbidden.

#### 7.1.1 Canonical plugin configuration key-space (host config)

Plugin configuration is host configuration and MUST be stored under:

-   plugins.<plugin_id>.config.<key>

#### 7.1.2 Plugin config default normalization (deterministic)

During plugin load, the host performs an explicit normalization step:

-   Inputs:
    -   plugin_id
    -   plugin manifest config_schema
-   Behavior:
    -   For each schema key missing under plugins.<plugin_id>.config:
        -   If the schema entry defines a default value (field "default"), write that default.
    -   Existing user values are never overwritten.
    -   If no keys are missing, no write occurs.
    -   Deterministic iteration order: lexicographic by schema key.
-   Storage:
    -   All writes go through ConfigService (no direct YAML access).

#### 7.1.3 Obsolete plugins.yaml

The legacy file "~/.config/audiomason/plugins.yaml" is obsolete/unsupported and MUST NOT be used
for plugin state or plugin configuration.

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

# 10. Import Wizard (Authoritative Integration)

This section formally integrates the Import Wizard consolidated model into the AudioMason2 authoritative specification.

Normative sources integrated here: Import Wizard Master Spec V3 through V11 (state machine, wire contracts, config governance, runtime model, persistence, performance, and deterministic enforcement).

This section is binding. If any implementation contradicts this section, the implementation is invalid unless this specification is updated first.

## 10.1 Identity and Scope

- Provided by plugin with manifest.name == "import".
- Implements PHASE 0 (preflight/discovery) and PHASE 1 (interactive wizard engine).
- Produces PHASE 2 job requests only; it MUST NOT execute PHASE 2 processing directly.
- UI layers (CLI/Web) are renderers only:
  - They render steps, collect inputs, submit payloads.
  - They MUST NOT implement validation, transitions, conflict scanning, job request generation, or any import-specific business logic.
- The system MUST remain functional if the import plugin is disabled or absent.

## 10.2 Three-Phase Enforcement (Import Wizard)

The wizard MUST follow the global three-phase model:

- PHASE 0: Preflight / discovery
  - No user interaction.
  - No jobs are created.
  - No mutation of processed registry.
- PHASE 1: User input
  - Interactive steps only.
  - No job creation.
  - No processing execution.
- PHASE 2: Processing
  - STRICTLY non-interactive.
  - Create jobs from canonical job_requests.json only.
  - No prompts, no questions, no UI calls.

Any violation is a hard contract error.

## 10.3 Authoritative State Machine (Steps and Transitions)

### 10.3.1 Workflow Authority (WizardDefinition)

The wizard state machine (step set and transition graph) is defined by the effective workflow snapshot
generated at session creation time.

Source artifacts:
- WizardDefinition (structural workflow): <wizards_root>/import/definitions/wizard_definition.json
- FlowConfig (non-structural tuning only): <wizards_root>/import/config/flow_config.json

At session creation, the engine MUST generate and persist the effective workflow snapshot into:
- sessions/<session_id>/effective_model.json

This effective snapshot is the single source of truth for the active session.

### 10.3.2 Mandatory Steps and Ordering Constraints

WizardDefinition MAY add, remove, reorder, or insert steps, but the engine MUST enforce mandatory
constraints to preserve phases and safety invariants.

Mandatory step_ids (MUST exist in every effective workflow):
S0  select_authors
S1  select_books
S2  plan_preview_batch (computed-only)
S10 conflict_policy
S12 final_summary_confirm
S14 processing (PHASE 2 terminal)

Mandatory ordering constraints (MUST hold):
- select_authors precedes select_books.
- select_books precedes plan_preview_batch.
- plan_preview_batch precedes conflict_policy.
- conflict_policy precedes final_summary_confirm.
- final_summary_confirm precedes processing.
- processing is the only PHASE 2 terminal step.

Optional steps MAY be inserted between mandatory steps, subject to Engine Guards (10.6) and phase rules.

### 10.3.3 Default Workflow

The default workflow provided by the system SHALL remain strictly linear and equivalent to the previous
canonical order, but it is now expressed as the default WizardDefinition rather than as a hardcoded list.
### 10.3.3 Deterministic Error Behavior (ERR/OK)

- ERR(payload): state MUST NOT advance; the current_step_id remains unchanged.
- OK(payload): state MUST advance deterministically to the next step (or next enabled step).

Special rule: plan_preview_batch error handling MUST be deterministic:
- If plan_preview_batch fails due to invalid or inconsistent selection, the engine MUST transition back to select_books.

### 10.3.4 Conditional Conflict Path

In final_summary_confirm:

- If confirm_start == false:
  - The state MUST remain final_summary_confirm (user must set true to proceed).
- If confirm_start == true AND conflict_mode != "ask":
  - Transition to processing.
- If confirm_start == true AND conflict_mode == "ask":
  - Engine MUST perform a conflict scan.
  - If conflicts exist: transition to resolve_conflicts_batch.
  - If no conflicts: transition to processing.

In resolve_conflicts_batch:
- ERR: remain resolve_conflicts_batch.
- OK: transition back to final_summary_confirm.

### 10.3.5 Renderer Neutrality (Hard Rule)

Renderers (CLI/Web) MUST NOT contain import-specific branching logic such as "if step_id == ...".
All step behavior (validation, transitions, conditional branching) MUST live in the wizard engine.

### 10.3.6 CLI Launcher and Renderer Configuration (Normative)

The CLI MAY provide an interactive renderer for the Import Wizard. This is UI-only.
It MUST delegate validation, transitions, conflict logic, and job request generation to the engine.

Behavior:
- The top-level command `audiomason import` is a CLI launcher for the renderer.
- Explicit subcommands `audiomason import wizard ...` and
  `audiomason import editor ...` MUST remain supported and unchanged.

Configuration (read via ConfigResolver):
- `plugins.import.cli.launcher_mode`: one of `interactive` | `fixed` | `disabled`.
  - `interactive` (default): `audiomason import` runs an interactive renderer and
    MAY prompt for root/path.
  - `fixed`: `audiomason import` runs the renderer without prompts using configured
    defaults.
  - `disabled`: `audiomason import` MUST print usage (legacy behavior) and MUST NOT
    start the renderer.
- `plugins.import.cli.default_root`: default RootName for session creation (default:
  `inbox`).
- `plugins.import.cli.default_path`: default relative path under the selected root
  (default: empty string).
- `plugins.import.cli.noninteractive`: if true, the renderer MUST NOT prompt and MUST
  fail if required inputs are missing.
- `plugins.import.cli.render.confirm_defaults`: if true, Enter MAY accept defaults
  when prompting (default: true).
- `plugins.import.cli.render.show_internal_ids`: if true, the renderer MAY display
  internal ids (default: false).
- `plugins.import.cli.render.max_list_items`: max items displayed in interactive lists
  (default: 200).

CLI overrides:
- The launcher MAY accept CLI flags that override the resolver values for the current run.
- Precedence MUST be: CLI flags > resolver config > hard-coded defaults.
- The launcher MUST provide a way to force legacy usage output for a single run
  (e.g. `--no-launcher` or `--launcher disabled`).

Root/path rules:
- Root MUST be validated against RootName (file_io roots).
- Path MUST be a relative path and MUST NOT contain `..`.
- Any filesystem listing performed by the renderer MUST be done via FileService and
  RootName (no direct filesystem access).


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
   - Returns the current FlowConfig JSON.

3) POST /import/ui/config
   - Validates and persists FlowConfig (full replace or supported patch mode).
   - Returns the saved FlowConfig.
   - On error returns the Error JSON schema (10.4.1).

4) POST /import/ui/config/reset
   - Resets FlowConfig to built-in defaults.
   - Persists and returns the FlowConfig.

5) POST /import/ui/session/start
   - Body: { "root": "<root-name>", "path": "<relative-path>", "mode": "stage" | "inplace" }
   - Starts a new wizard session and returns SessionState.

6) GET  /import/ui/session/{session_id}/state
   - Returns SessionState for an existing session.

7) POST /import/ui/session/{session_id}/step/{step_id}
   - Submits a step payload and returns updated SessionState.

8) POST /import/ui/session/{session_id}/start_processing
   - Body: { "confirm": true }
   - Finalizes PHASE 1 and returns a summary: { "job_ids": [...], "batch_size": <int> }
   - MUST enforce deterministic conflict re-check before job creation (10.11.4).

Optional (only if implemented): config history and rollback endpoints.
If implemented, they MUST be deterministic and atomic.

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

## 10.7 Storage Model (File IO Root) and Artifacts

All Import Wizard data MUST be stored under the file_io root:

<wizards_root>/import/

Required subpaths:

- catalog/catalog.json
- flow/current.json
- config/flow_config.json
- sessions/<session_id>/effective_model.json
- sessions/<session_id>/effective_config.json
- sessions/<session_id>/discovery.json
- sessions/<session_id>/state.json
- sessions/<session_id>/decisions.jsonl
- sessions/<session_id>/plan.json
- sessions/<session_id>/job_requests.json
Notes:
- sessions/<session_id>/effective_model.json MUST contain the frozen effective workflow snapshot derived from WizardDefinition and FlowConfig.
  UI layers MUST NOT interpret global WizardDefinition directly for an active session.
  For select_authors and select_books, effective_model.json MUST include items[] for the
  multi_select_indexed selection fields.


Engine-derived artifacts (engine-owned; may be created deterministically):

- sessions/<session_id>/action_jobs.json
  - Meaning: canonical job requests for action steps with execution="job" within PHASE 1.
  - Contract: each entry MUST be canonical JSON and MUST be compatible with the job subsystem.
  - action_jobs.json MUST NOT be used for PHASE 2 processing jobs (see 10.11).

- previews/<preview_id>.json
  - Meaning: isolated preview_action result artifact (10.23 / 10.23 Preview Execution).
  - MUST NOT modify any session snapshot.

- sessions/<session_id>/discovery_fingerprint.txt
  - Content: <hex> + newline
  - Meaning: SHA-256 fingerprint of canonical JSON discovery set (10.8).

- sessions/<session_id>/effective_config_fingerprint.txt
  - Content: <hex> + newline
  - Meaning: SHA-256 fingerprint of canonical effective_config snapshot.

- sessions/<session_id>/conflicts.json
  - Content: canonical JSON list of conflict items.
  - Meaning: persisted conflict snapshot used by deterministic conflict re-check.

- sessions/<session_id>/idempotency.json
  - Content: canonical JSON object tracking idempotency_key mappings for job creation.
  - Meaning: prevents duplicate job creation for repeated start_processing calls.

If present, these artifacts MUST be written atomically (temp + rename).


Creation timing:
- plan.json MUST be created/updated by compute_plan (10.11).
- job_requests.json MUST be created only when start_processing is accepted and a job is requested
  (10.11.4).

plan.json baseline schema additions (normative):
- selected_books: list of selected book units (book_id, label, source_relative_path,
  proposed_target_relative_path)
- summary.selected_books: count of selected books
- summary.discovered_items: count of discovery items

Resume-after-restart is mandatory where specified by runtime mode policy (10.9).
All writes MUST be atomic (write temp, then rename).

### 10.7.1 Model Bootstrap When Missing

If catalog/catalog.json, flow/current.json, or config/flow_config.json do not exist under the
file_io root "wizards", the import plugin MUST deterministically bootstrap them from built-in
defaults.

Bootstrap rules:
- Creation MUST be atomic (write temp, then rename).
- Existing files MUST NOT be overwritten.
- Bootstrapped models and config MUST pass full model validation.
- Bootstrap MUST occur before first model load.
- Absence of models MUST NOT cause a hard failure if bootstrap succeeds.


## 10.8 Deterministic Discovery (PHASE 0)

Discovery MUST produce a canonical discovery input set.

Each item MUST contain:
- item_id
- root
- relative_path
- kind (file|dir|bundle)

Bundle classification rules:
- kind MUST be "bundle" for files whose relative_path ends with one of:
  .zip, .tar, .tgz, .tar.gz, .tar.bz2, .rar
- Extension matching MUST be case-insensitive.

Canonical ordering:
1) root (ASCII lexicographic)
2) relative_path (ASCII lexicographic)
3) kind

item_id MUST equal:
root:<root>|path:<relative_path>

relative_path MUST:
- use "/" separators
- contain no ".", "..", empty segments, or leading slash

discovery_fingerprint MUST equal:
SHA-256(canonical JSON discovery set)

Persisted per session in:
state.derived.discovery_fingerprint

## 10.9 Session Snapshot Isolation and Persistence Model

At session start, the engine MUST create an immutable snapshot:
- effective_config.json (FlowConfig snapshot for the session)
- effective_model.json (FlowModel snapshot for the session)

Active sessions MUST use their snapshot for their entire lifetime.
Configuration changes MUST affect only new sessions.

Persistence requirements:
- Web mode: full session persistence on disk is mandatory (crash recovery required).
- CLI mode: full session persistence may be in-memory, but snapshot semantics still apply.

## 10.10 Determinism Closure (Session Identity Tuple)

A session is deterministically defined by:
- model_fingerprint (SHA-256 over canonical effective_model.json)
  - model_fingerprint MUST be computed over the final persisted effective_model.json
    after all enrichment steps (for example, selection items injection).
- discovery_fingerprint
- effective_config_fingerprint (SHA-256 over canonical effective_config.json)
- validated user inputs (canonical forms)

Finalize MUST produce byte-identical canonical job_requests.json for identical tuples.


## 10.10A PHASE 1 Action Job Request Schema (Normative)

For action steps with execution == "job", the interpreter MUST create entries
inside:

sessions/<session_id>/action_jobs.json

Each entry MUST conform EXACTLY to the canonical job request schema defined
in Section 10.11 (Job Request Contract - PHASE 2).

Normative rules:

- The JSON structure MUST match the same schema used by PHASE 2 processing jobs.
- No additional keys MAY be introduced.
- Required keys MUST NOT be omitted.
- job_id generation MUST follow the same deterministic rules as PHASE 2 jobs.
- action_jobs.json is limited strictly to PHASE 1 action steps.
- PHASE 2 processing jobs remain governed exclusively by Section 10.11.

Any deviation from the canonical Job Request schema SHALL be treated as
CONTRACT_VIOLATION.

------------------------------------------------------------------------

## 10.11 Job Request Contract (PHASE 2)

job_requests.json MUST contain:
- config_fingerprint (SHA-256 over canonical effective_config.json)
- job_type
- job_version
- session_id
- actions[]
- diagnostics_context

All file references MUST use (root, relative_path).
Absolute paths are forbidden.

actions[] contract (normative):
- actions[] MUST be derived from sessions/<session_id>/plan.json.
- actions[] MUST contain one entry per planned unit (selected_books[]).
- If selected_books[] is empty and plan.source.relative_path is non-empty, actions[] MUST contain exactly one implicit unit.

start_processing response contract (normative):
- start_processing MUST return batch_size equal to the number of planned units represented in job_requests.json actions[].

### 10.11.1 Canonical Serialization (Mandatory)

All job request serialization MUST be canonical:
- JSON keys sorted
- books (or per-book entries) sorted by canonical key (book_id or stable (root,relative_path) key)
- paths normalized (no duplicate separators; no traversal segments)
- no volatile fields (timestamps, random IDs) in canonical output

A shared canonical_serialize utility MUST exist and MUST be used by:
- golden tests
- parity comparisons (if any)
- job_requests.json persistence

### 10.11.2 Idempotency Key (Mandatory)

Each created job MUST have a deterministic idempotency_key.

Recommended formula:
hash(book_id + canonical_config_snapshot)

Rules:
- Duplicate job creation with the same idempotency_key MUST be prevented.
- Duplicate start_processing calls MUST not create duplicate jobs.
- Registry updates MUST remain safe under retries.

### 10.11.3 Registry Updates (SUCCESS-only)

The processed registry MUST be updated only when the corresponding job finishes with SUCCESS.
FAILED jobs MUST NOT update the registry.

### 10.11.4 Conflict Re-check Before Job Creation (Mandatory)

Before creating jobs:
- If conflict_mode == "ask": re-run conflict scan and abort if unresolved conflicts remain.
- If conflict_mode != "ask": ensure no new filesystem conflicts appeared since preview.

Conflict scan inputs (normative):
- conflict scan MUST use planned target outputs from sessions/<session_id>/plan.json
  (selected_books[].proposed_target_relative_path) rather than raw discovery.
- conflict items MUST be deterministically sorted by:
  1) target_relative_path (ASCII lexicographic)
  2) source_book_id (ASCII lexicographic)
- minimal conflict item schema:
  - target_relative_path
  - reason (exists|unknown)
  - source_book_id

If conflicts appear, the engine MUST block processing deterministically and return a structured error.

## 10.12 Config Governance (Editors and Storage)

If visual editors exist:

- A Wizard editor modifies WizardDefinition only (structural workflow).
- A Config editor modifies FlowConfig only (non-structural tuning).

Requirements:
- Validate FlowConfig on load, save, import, and preset apply.
- Prevent saving invalid config (invariant violations).
- Support reset to built-in defaults.
- If history/rollback is implemented:
  - keep deterministic history with bounded retention N=5 (MANDATORY)
  - allow deterministic rollback to a selected historic version
- Defaults memory (if implemented) MUST NOT update implicitly.
  - Only explicit user action may update defaults.
  - Any auto-save (if implemented) MUST be visible and reversible via history.

## 10.13 Performance and Scaling (Deterministic)

Performance rules are non-functional constraints but MUST NOT alter outputs.

- FlowModel build must be lightweight.
- Selection parser must be linear time.
- plan_preview_batch output MUST be bounded by preview_limit and MUST surface truncation explicitly.
- conflict scan SHOULD be optimized with precomputed target path maps when feasible.
- parallelism MUST be bounded by a hard MAX_PARALLELISM limit in the engine (implementation-defined but fixed).

Caches (if implemented):
- cache keys MUST be deterministic
- cache miss MUST recompute (never silently fail)
- enabling/disabling cache MUST NOT change job_requests output

## 10.14 Diagnostics (Mandatory)

The import engine MUST emit via the Core authoritative diagnostic entry point:

- session.start
- session.resume
- model.load
- model.validate
- step.submit
- plan.compute
- finalize.request
- job.create

Diagnostics MUST include at minimum:
- session_id
- model_fingerprint
- discovery_fingerprint
- effective_config_fingerprint

## 10.15 Testing and Enforcement (Hard Gates)

The repository MUST include deterministic tests that enforce:

- FlowBuilder invariants and mandatory step preservation.
- Selection expression parser grammar and error behavior.
- Session transitions: ERR does not advance; OK advances deterministically.
- Conflict ask batch behavior (final_summary_confirm -> resolve_conflicts_batch).
- Phase enforcement (no jobs in PHASE 1; no step submits in PHASE 2).
- Registry SUCCESS-only.
- Canonical serialization stability (golden job_requests comparisons).
- Renderer neutrality (static enforcement forbidding import-specific branching in UI layers).
- Single source of truth for step ordering (BaseFlowDefinition defined exactly once).
- Session snapshot isolation (config changes do not affect active sessions).
- Conflict re-check before job creation.
- Idempotency key enforcement (no duplicate jobs).

Integration completed (updated): 2026-02-18 06:00:00 UTC

------------------------------------------------------------------------

## 10.16 Structural Workflow Authority (WizardDefinition Model)

The Import Wizard structural workflow MUST be defined by a single authoritative
artifact named WizardDefinition.

Location (file_io root: wizards):

<wizards_root>/import/definitions/wizard_definition.json

Rules:

- WizardDefinition defines structural workflow only:
  - step ordering
  - step types
  - structural transitions
  - action bindings
- FlowConfig MUST NOT modify structure.
- FlowConfig MAY modify only non-structural parameters (see 10.4.4).
- WizardDefinition MUST be versioned and validated on load.
- Structural edits affect only new sessions.

Active sessions MUST use a frozen effective_workflow snapshot.

------------------------------------------------------------------------

## 10.17 Interpreter Authority (Single Execution Engine)

The Import Wizard MUST use a single interpreter responsible for:

- Step transitions
- Validation
- Conflict evaluation
- Action execution
- Job request generation

UI layers (CLI/Web) MUST:

- Render step payload only
- Submit user input
- Never branch on step_id
- Never execute plugin logic directly

Any UI-level business logic is a contract violation.

------------------------------------------------------------------------

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
