
# AudioMason2 - Project Specification (Authoritative)

Specification Version: 1.0.49
Specification Versioning Policy: Start at 1.0.0. Patch version increments by +1 for every change.


Author: Michal Holes  
Status: **AUTHORITATIVE / BINDING**  
Applies to: AudioMason2 core, plugins, tooling, UI, tests, documentation  
Language: **English (mandatory for all repository content)**

---

## 1. Purpose of This Document

This document is the **authoritative specification** for the AudioMason2 (AM2) project.

Its role is to:

- define **what AudioMason2 is and must be**,
- establish **non?negotiable architectural and behavioral rules**,
- act as a **binding contract** for all future development,
- prevent architectural drift, monolith growth, and ad?hoc fixes,
- ensure long?term maintainability, testability, and extensibility.

Any implementation, patch, refactor, or feature **must comply with this specification**.

If a change contradicts this document, the change is **invalid** unless the specification itself is updated and approved first.

---

## Specification Versioning and Change Log

This specification is versioned. The version is tracked near the top of this document.

Rules:

- Start at version 1.0.0.
- Every change to this specification MUST increment the patch number by +1 (e.g. 1.0.0 -> 1.0.1).
- Every change delivered by a patch MUST be recorded in docs/changes.md.
- Each change entry in docs/changes.md MUST start with an ISO 8601 timestamp captured at patch creation time.

### docs/changes.md - Canonical Change Log Format (MANDATORY)

The file docs/changes.md is a **pure chronological change log**.

It MUST contain:
- only ISO 8601 timestamps and human-readable descriptions of changes,
- entries ordered strictly by time (newest first or oldest first, but consistent),
- one or more change descriptions per timestamp.

It MUST NOT contain:
- issue numbers or issue references,
- issue groupings or headings (e.g. "Issue 123"),
- patch IDs, commit hashes, or author names,
- explanations of motivation, discussion, or process.

docs/changes.md records **what changed and when**, nothing else.
Process tracking (issues, discussions, rationale) belongs elsewhere.


## 2. Core Vision

AudioMason2 is a **general?purpose, plugin?driven, asynchronous media processing platform** with a strong focus on:

- audiobooks (primary use case),
- deterministic behavior,
- user?controlled workflows,
- extensibility through plugins,
- multiple user interfaces (CLI, Web, Daemon),
- long?term evolvability without rewrites.

AM2 is not a collection of scripts.  
AM2 is an **engine + ecosystem**.

---

## 3. Fundamental Principles (Non?Negotiable)

### 3.1 Ultra?Minimal Core

- Core contains **infrastructure only**, never business logic.
- Core must remain small, readable, and stable.
- Core responsibilities:
  - plugin loading and orchestration
  - configuration resolution
  - job orchestration
  - pipeline execution infrastructure
  - error and phase enforcement

Core must **never**:
- implement audio processing
- implement metadata fetching
- implement UI logic
- implement storage backends

Everything else is a plugin.

---

### 3.2 Plugin?First Architecture

- Plugins are the primary extension mechanism.
- Core depends on **interfaces**, never concrete implementations.
- Plugins may add, modify, or disable behavior.
- Plugins must be isolatable and removable without breaking the system.

No feature may be added directly to core if it can exist as a plugin.

---

### 3.3 Deterministic Behavior

- Same inputs + same config = same outputs.
- No hidden state.
- No time?dependent logic unless explicitly modeled.
- All behavior must be observable via logs and job state.

---

### 3.4 Asynchronous by Design

- Long?running operations must be asynchronous.
- UI must never block on processing.
- Progress and logs must be observable while work is running.

Synchronous shortcuts are forbidden except for trivial operations.

---

## 4. Execution Model (Strict Contract)

### 4.1 Three?Phase Model

All processing follows **exactly** these phases:

1. **PHASE 0 - Preflight**
   - Detection only
   - Read?only
   - No side effects
   - No user interaction

2. **PHASE 1 - User Input**
   - Interactive
   - UI?controlled (CLI/Web)
   - All decisions are collected here

3. **PHASE 2 - Processing**
   - **STRICTLY NON?INTERACTIVE**
   - Async background execution
   - No prompts, no questions, no UI calls

Violation of phase boundaries is a **hard error**.

---

### 4.2 Phase Enforcement

- Phase rules are enforced centrally in core.
- Any attempt to interact with the user during PHASE 2 must:
  - raise a contract violation error,
  - fail the job deterministically,
  - preserve partial results and checkpoints if possible.

---

## 5. Job Model (Mandatory)

### 5.1 Jobs as the Only Execution Unit

- Every operation that does work is a **Job**.
- UI layers may only:
  - create jobs
  - observe jobs
  - cancel jobs

UI layers may **never** execute pipelines directly.

---

### 5.2 Job Properties

Each job has at minimum:

- unique job_id
- type (process, wizard, daemon, etc.)
- state (PENDING, RUNNING, SUCCEEDED, FAILED, CANCELLED)
- progress (0.0-1.0)
- timestamps
- bound log stream

---

### 5.3 Job Persistence

- Jobs must be persisted.
- Storage backend is abstracted and replaceable.
- Loss of job state after restart is unacceptable.

---

## 6. Configuration System

### 6.1 Single Access Path

- All runtime configuration access goes through **ConfigResolver API**.
- No component may read configuration files directly.

---

### 6.2 Priority Rules

Configuration priority is fixed and mandatory:

1. CLI arguments  
2. Environment variables  
3. User configuration  
4. System configuration  
5. Defaults  

The source of each resolved value must be traceable in debug mode.

---


### 6.3 Configuration Schema Registry

- ConfigResolver must expose an authoritative schema registry for known configuration keys.
- Each schema entry must define at minimum:
  - key_path (dot notation, e.g. "web.port")
  - value_type ("string" | "int" | "bool" | "enum" | "list" | "object" | "path")
  - description (ASCII-only)
  - default (if defined)
  - enum_values (only for enum)

UI and other layers consume the schema through resolver APIs. UI is never a source of truth.

---

### 6.4 Deterministic Key Enumeration

- Resolver must provide a deterministic list of known keys:
  - `list_known_keys() -> list[str]` returns schema keys sorted lexicographically.
- `resolve_all()` must enumerate at least all known keys from the schema.

---

### 6.5 Unknown Keys Policy (Compatibility)

- Unknown keys (keys not present in the schema registry) are permitted for compatibility.
- Unknown keys are treated as type `any`:
  - no type validation is applied by resolver
  - admin tooling may surface them as "unknown/advanced"
- Unknown keys must not make the resolver non-deterministic.

---

### 6.6 Minimal Type Validation (Known Keys)

- Known keys (present in schema) must support minimal type validation:
  - int: must be int (no implicit string coercion unless schema explicitly allows it)
  - bool: must be bool (no implicit string coercion unless schema explicitly allows it)
  - enum: must be one of the allowed enum values
  - path: baseline is string (no filesystem checks in this baseline)

---

### 6.7 Canonical Logging Verbosity

Canonical key:
- `logging.level`

Allowed values (after normalization):
- `quiet`
- `normal`
- `verbose`
- `debug`

### 6.7.1 Human-Readable System Log File

Core does not implement a file-backed system log backend. Instead, Core emits a human-readable log stream via a Core-owned publish/subscribe bus called LogBus.

Semantics:
- Every log line emitted by the Core logger is published to LogBus as a LogRecord (plain, no colors, no trailing newline).
- If no subscribers exist, publishing is a no-op (logs are effectively dropped).
- If a subscriber raises, the exception is suppressed and reported to stderr; the system must not crash.

Persistence semantics:
- Log persistence is performed by external subscribers (plugins) that subscribe to LogBus.
- Persistence MUST use the File I/O capability (and its roots). UI layers must not write to arbitrary filesystem paths directly.
- If no persistence subscriber exists, no human-readable system log file is created or updated.

Diagnostics note:
- LogBus is a log streaming mechanism only. It is NOT the authoritative runtime diagnostic emission entry point. Diagnostic lifecycle events remain exclusively emitted via the existing Core diagnostic entry point as specified elsewhere in this document and in the base project contract.

---

### 6.7.2 Syslog plugin

The syslog plugin is a LogBus subscriber that persists Core log records to a
file under the file_io CONFIG root. Core remains independent of this plugin.

Behavior:
- Subscribes to LogBus only when enabled.
- Persists records via file_io (no direct filesystem access in the plugin).
- Append-only file semantics.

Configuration (preferred, plugin-scoped):
- plugins.syslog.enabled: bool (default false)
- plugins.syslog.filename: string (default "logs/system.log")
- plugins.syslog.disk_format: string (default "jsonl"; allowed: jsonl, plain)
- plugins.syslog.cli_default_command: string (default "tail"; allowed: tail, status, cat)
- plugins.syslog.cli_default_follow: bool (default true)

Legacy alias fallback (used only when plugins.syslog namespace is not present):
- logging.system_log_enabled -> plugins.syslog.enabled
- logging.system_log_filename -> plugins.syslog.filename
- logging.system_log_format -> plugins.syslog.disk_format

Priority:
- If the plugins.syslog namespace exists, legacy aliases are ignored.
- If disk_format is unknown, the plugin disables itself (enabled=false), emits a
  warning, and emits a diagnostic FAIL event.

Disk formats:
- plain: append one human-readable line per record.
- jsonl: append one JSON object per record (JSON Lines).

JSONL schema (stable minimum):
- level: string
- logger: string
- message: string
- ts: string or null (only if provided by the record; do not synthesize time)

Failure isolation:
- Subscriber callbacks must catch all exceptions.
- After 3 consecutive write failures, the plugin unsubscribes from LogBus, emits
  one warning, emits a diagnostic FAIL event, and stops writing.

CLI:
- audiomason syslog: runs the configured default command (default tail).
- Subcommands: status, cat, tail.
- tail supports --lines N (default 50), --follow, --no-follow, and --raw.
- tail follow mode must not print periodic waiting messages; it blocks silently.
- Missing log file for cat/tail results in a human error message, non-zero exit
  code, and a diagnostic FAIL event.

Diagnostics:
- The plugin must not publish to LogBus.
- The plugin must emit lifecycle and CLI diagnostics via the authoritative Core
  diagnostic entry point (START/END/FAIL), and this emission must be fail-safe.

---

### 6.8 ConfigService Mutation Primitives

UI layers must not edit raw YAML directly. If a UI needs to mutate user configuration, it must use ConfigService.

ConfigService provides two execution primitives:

- `set_value(key_path, value)`
  - writes a single key path into the user config YAML
  - unknown keys are allowed and are not validated
  - minimal validation is applied only for `logging.level` (quiet|normal|verbose|debug)

- `unset_value(key_path)`
  - removes a single key path from the user config YAML (reset to inherit)
  - prunes empty parent mappings recursively
  - idempotent: unsetting a missing key is a no-op

ConfigService must re-initialize the resolver after each mutation so subsequent reads reflect the change deterministically.

Normalization rules:
- value must be a string
- trim whitespace
- lowercase
- empty string is invalid

Default semantics:
- If no source provides `logging.level`, resolver returns `normal`.

Failure semantics:
- Resolver raises ConfigError if value is non-string, empty/whitespace, or not in the allowed set.

---


### 6.4 Resolved LoggingPolicy

The configuration resolver MUST provide a canonical, structured logging policy
derived from the canonical verbosity key. This ensures that the meaning of
verbosity is defined in exactly one place.

Type: LoggingPolicy (immutable)

Fields:
- level_name: str
  - One of: quiet | normal | verbose | debug
- emit_error: bool
- emit_warning: bool
- emit_info: bool
- emit_progress: bool
- emit_debug: bool
- sources: dict[str, ConfigSource]
  - Must include the source for level_name under the key "level_name".

Semantics (derived deterministically from level_name):

quiet:
- emit_error = True
- emit_warning = True
- emit_info = False
- emit_progress = False
- emit_debug = False

normal:
- emit_error = True
- emit_warning = True
- emit_info = True
- emit_progress = True
- emit_debug = False

verbose:
- emit_error = True
- emit_warning = True
- emit_info = True
- emit_progress = True
- emit_debug = False

debug:
- Same as verbose, except:
- emit_debug = True

Alias rules (resolver-only):
- The legacy key "verbosity" is treated as an alias for "logging.level".
- If both are present, "logging.level" ALWAYS wins.
- Consumers MUST NOT be aware of aliases.

CLI input rules:
- CLI MUST set the canonical key logging.level (nested: logging.level).
- CLI MUST NOT set the resolver-only alias verbosity.

Guarantees:
- resolve_logging_policy() is deterministic and side-effect free.
- No numeric levels and no coupling to any logging library.

---

## 7. Plugin System Specification

### 7.1 Plugin Registry

- There must be a single **PluginRegistry API**.
- It is the only source of truth for:
  - discovery
  - enable/disable state
  - plugin configuration
  - metadata

Multiple parallel plugin state mechanisms are forbidden.

---

### 7.2 Plugin Isolation

- Plugin failure must not crash the system.
- A failed plugin may be skipped with a warning.
- Plugins must not assume filesystem layout or config storage.

---

### 7.3 Plugin Installation Rules

- Runtime mutation of repository plugins is forbidden.
- User?installed plugins live in user plugin directories only.
- Installation mechanism must be abstracted.



### 7.3.1 Built-in Plugin Import Path Rules (Loader Responsibility)

- Built-in plugin loading MUST work without requiring the user to set PYTHONPATH.
- When loading built-in plugins from the repository 'plugins/' package, the core plugin loader MUST ensure
  the repository root is present on sys.path so that absolute imports like 'plugins.*' are resolvable.
- This rule applies only to built-in plugins. Loading plugins from user/system plugin directories MUST NOT
  implicitly grant repository-root import privileges.

### 7.4 File I/O Capability (Plugin-Owned)

- File operations are provided by the `file_io` plugin as a reusable capability.
- UI layers (CLI, Web, TUI) must not implement filesystem logic; they call this capability.
- Core must not implement a storage backend; file I/O remains plugin-owned.

#### 7.4.1 Roots

The file I/O capability must support named roots:

- inbox: input drop area for new sources
- stage: general staging area (non-job-specific)
- jobs: isolated per-job workspaces
- outbox: outputs intended for download/export
- config: configuration-owned filesystem data (optional)
- wizards: wizard-owned filesystem data

#### 7.4.2 Operations

The capability must provide, at minimum:

- list_dir (stable deterministic order)
- stat
- exists
- open_read (download streaming)
- tail_bytes (download tail primitive)
- open_write (upload streaming)
- open_append (upload streaming append-only)
- mkdir (parents supported)
- rename (move)
- delete_file
- rmdir (empty directories only)
- rmtree (recursive delete)
- copy
- checksum (sha256 default)


Append rules:

- Append is a byte-level primitive (callers provide bytes; no formatting).
- The file I/O capability must not implement rotation, size limits, or flush policy.

Tail rules:

- tail_bytes is a byte-level primitive (callers interpret bytes; no decoding).
- The file I/O capability must not implement follow, rotation, formatting, or line parsing.

#### 7.4.3 Determinism Rules

- list_dir ordering must be stable and deterministic (lexicographic by relative path).
- checksum must be deterministic (sha256 over file bytes).
- The file service itself must not generate random or time-based names.

#### 7.4.4 Separation From Pipeline Semantics

- Pipeline steps (import/export/extract/preflight) may use the file capability.
- Naming policy and cleanup policy are part of pipeline behavior, not the core file capability.


#### 7.4.5 Archive Capability (Plugin-Owned)

The file I/O plugin must provide an archive capability built on top of the file roots.

This capability must support:

- pack: create an archive from a directory under a root
- unpack: extract an archive under a root into a destination directory under a root
- plan_pack and plan_unpack: return a deterministic plan without executing changes
- detect_format: optional helper, executed only when explicitly requested by higher layers

Required behavior:

- The higher layer must be able to specify the exact archive filename to create.
- The higher layer must be able to specify the destination directory name to unpack into.
- The higher layer must be able to choose:
  - preserve_tree: keep the directory structure inside the archive
  - flatten: extract all files into a single directory
- When flattening, the higher layer must be able to select a collision policy:
  - error: fail on name collisions
  - rename: deterministically rename collisions with __N suffixes
  - overwrite: overwrite existing destination files

Format support:

- ZIP (pack and unpack, deterministic pack)
- TAR, TAR.GZ, TAR.XZ (pack and unpack, deterministic pack)
- RAR (unpack is required; pack is best-effort and may depend on external tools)

Determinism note:

- Deterministic pack output is guaranteed for the stdlib ZIP/TAR backends.
- RAR pack may not be deterministic across tools/versions and is best-effort.

Debug/trace support:

- The archive capability must be able to emit a structured operation trace, including planned and ok/error phases,
  when explicitly enabled by configuration or request parameters.



---

---

### 7.5 CLI Plugin Command Extension

This section defines the contract for extending the AudioMason2 CLI with plugin-provided commands.

This mechanism is strictly limited to adding new CLI commands. Plugins MUST NOT modify, override,
intercept, or disable existing CLI commands.

This section intentionally defines stricter constraints for CLI extensibility than the general plugin
capability model described elsewhere in this specification.

#### 7.5.1 Ownership and Responsibility

- CLI command extensibility is owned by the CLI plugin.
- Core MUST NOT provide a global CLI hook bus.
- Core responsibilities end at plugin discovery, manifest loading, and enable/disable state via
  PluginRegistry.

#### 7.5.2 Declaration Contract

Plugins that provide CLI commands MUST explicitly declare this capability via a dedicated interface.

- The canonical interface name is: ICLICommands
- Plugins that do not declare this interface MUST be ignored for CLI command registration.
- Implicit or heuristic detection is forbidden.

#### 7.5.3 Discovery Sources

The CLI plugin MAY discover CLI command providers from all supported plugin sources:

- built-in plugins
- user plugins
- system plugins

Discovery MUST be deterministic and independent of filesystem enumeration order.

#### 7.5.4 Loading Model

A hybrid loading model is required:

- At CLI startup, the system MUST perform lightweight discovery (manifest reads, validation, and
  command stub preparation).
- Full plugin import and initialization MUST NOT occur until the corresponding CLI command is invoked.
- Manifest-only discovery MUST NOT execute plugin code.

#### 7.5.5 Command Name Rules

Plugin-provided CLI command names MUST be globally unique.

- Command name collisions are FORBIDDEN.
- Any collision MUST result in a deterministic error.
- Silent overrides or filesystem-order resolution are prohibited.

#### 7.5.6 Failure Isolation

Failure of a CLI command plugin MUST NOT crash the CLI.

- A plugin that fails during loading or execution MUST be disabled for the current session.
- Other CLI commands MUST remain available.
- Errors SHOULD be reported clearly to the user.

#### 7.5.7 Enable / Disable Semantics

CLI command registration MUST respect PluginRegistry.

- Disabled plugins MUST NOT register CLI commands.
- Plugin enable/disable state is authoritative and centralized.

#### 7.5.8 User Visibility

The origin of every plugin-provided CLI command MUST be visible to the user.

- Help output MUST indicate the providing plugin for each plugin-provided command.
- Anonymous or hidden command registration is forbidden.

#### 7.5.9 Determinism Requirements

All CLI plugin command behavior MUST be deterministic.

- Plugin processing order MUST be explicitly defined and stable.
- Filesystem order MUST NOT affect behavior.
- Help output, command lists, and error messages SHOULD be stable across runs.


### 7.5.10 ICLICommands Interface Contract

Plugins that declare the `ICLICommands` interface MUST implement the following Python-level contract.

The plugin class MUST expose a method:

`get_cli_commands() -> dict[str, Callable]`

Normative requirements:

- Dictionary keys MUST be CLI command names.
- Command names MUST:
  - be lowercase,
  - contain only ASCII letters, digits, and hyphens,
  - not conflict with existing core CLI commands.
- Dictionary values MUST be callables.
- Callables MUST accept a single argument: `argv: list[str]`.
- Callables MAY be synchronous or asynchronous.
- The CLI host MUST transparently support both sync and async handlers.
- The CLI host MUST NOT call `get_cli_commands()` until the command is invoked.

### 7.5.11 Deterministic Discovery and Ordering Rules

All CLI command plugin discovery MUST be deterministic.

Mandatory rules:

1. Plugin discovery directories MUST be processed in this order:
   1. built-in plugins
   2. user plugins
   3. system plugins

   The CLI host MUST preserve this source ordering when iterating discovered plugin directories.
   The CLI host MUST NOT globally re-sort the combined discovered list across sources.

2. Within each directory:
   - plugin directories MUST be sorted lexicographically by directory name.
   - Sorting key MUST be the directory name (Path.name).

3. For command registration:
   - plugins MUST be ordered by `manifest.name` (lexicographically).
   - filesystem iteration order MUST NOT influence behavior.

4. If two plugins declare the same CLI command name:
   - this is a fatal configuration error,
   - the CLI MUST abort startup with a clear error message.

### 7.5.12 CLI Command Stub Registry

The CLI plugin MUST maintain an internal registry of CLI command stubs.

A command stub MUST contain:
- command name,
- providing plugin identifier (`manifest.name`),
- a reference sufficient to lazily load the plugin.

Manifest requirement (Phase 2):

- For plugins that declare `ICLICommands`, the plugin manifest (`plugin.yaml`) MUST declare
  the command names under `cli_commands: [<command-name>, ...]`.
- This list MUST be used to build the stub registry and help output without importing plugin code.
- If `ICLICommands` is not declared, `cli_commands` MUST be ignored.

At CLI startup:
- only stubs MAY be registered,
- plugin code MUST NOT be imported.

On command invocation:
- the CLI MUST load exactly one plugin,
- call `get_cli_commands()`,
- resolve the requested command,
- execute its handler.

Phase 3 implementation requirement:
- The built-in CLI plugin MUST execute plugin-provided CLI commands by following this contract.

### 7.5.13 Failure Semantics for Command Invocation

If a CLI command plugin fails during load or execution:

- the failure MUST NOT crash the CLI process,
- the plugin MUST be marked as failed for the current session,
- subsequent invocations MUST be rejected with a clear error,
- other CLI commands MUST remain functional.

Failure of one plugin MUST NOT affect discovery or execution of other plugins.

### 7.5.14 Help and User-Facing Output Format

The CLI help output MUST distinguish core commands from plugin commands.

For plugin-provided commands, the following format is mandatory:

`<command-name>    (plugin: <plugin-name>)`

The ordering of help output MUST be deterministic and stable across runs.

If a plugin command exists but its plugin failed to load:
- the command MUST still appear in help output,
- and MUST be annotated as unavailable.

### 7.5.15 Relationship to Core CLI Dispatch

Core CLI commands take precedence in name resolution.

Resolution order:
1. Core CLI commands
2. Plugin-provided CLI commands

Plugins MUST NOT override or shadow core commands.

Reserved core command names (plugins MUST NOT provide these names):
- process
- wizard
- web
- daemon
- checkpoints
- version
- help

Note: `tui` is not reserved and may be provided by plugins.

### 7.5.16 Reference Plugin: test_all_plugin

The repository includes a builtin reference plugin named `test_all_plugin`.

Purpose:

- Provide a canonical, deterministic "kitchen sink" example for plugin authors.
- Provide stable integration test coverage for the plugin loader and CLI command extension.

Location:

- `plugins/test_all_plugin/`

Required properties:

- Deterministic and non-interactive.
- Declares multiple interfaces (IProcessor, IEnricher, IProvider, IUI, ICLICommands).
- Declares `cli_commands` and provides handlers via `get_cli_commands()`.

## 8. Wizard System

### 8.1 Wizard Service

- All wizard access goes through **WizardService API**.
- UI must not manipulate wizard files directly.

Wizard storage rules:

- All wizard definitions are stored under the file_io root `wizards`.
- WizardService MUST store definitions under: `definitions/<name>.yaml`.
- No component may read/write wizard YAML definitions using direct filesystem calls
  (no pathlib, no open()); all CRUD must go through the file_io capability.

---

### 8.2 Wizard Execution

- Wizard execution produces jobs.
- Wizard UI interaction happens only in PHASE 1.
- Processing follows standard pipeline rules.

Async execution rule:

- WizardEngine is async-only.
- It is a BUG for wizard execution to call async plugin methods through sync wrappers
  (e.g., nested `asyncio.run` within an existing event loop). Such violations MUST be
  made explicit by failing fast.

Async execution rules:

- Wizard execution MUST be async-safe (no nested event loops, no asyncio.run() inside
  a running loop).

---



### 8.3 Import Wizard Foundation (Infrastructure Only)

The Import Wizard is implemented as a WizardSystem-anchored workflow.

Rules:

- Wizard definition remains the single source of truth (WizardService / WizardEngine).
- Import runtime state is a wizard-run scoped artifact keyed by wizard job id (run id).
- PHASE 0 preflight is deterministic and read-only.
- Processed tracking is performed by a book-folder registry (no inbox markers, no inbox writes).

The foundational infrastructure for Import Wizard MUST live in plugins/import/ and MUST use file_io capability only.

Required components:

- session_store: Persist ImportRunState under the file_io JOBS root.
- preflight: Deterministic read-only detection producing a list of discovered book units (mixed inbox layout support), cover candidates, rename preview map, a stable book_ref per unit, explicit skipped entries (with reason), and a basic unit fingerprint.
- processed_registry: Book-folder processed registry under the file_io JOBS root.

Issue 403 extension (PHASE 2 processing engine):

- import engine MUST create persisted Jobs for PHASE 2 processing (no UI dependency).
- engine MUST expose a stable service API callable from CLI and Web:
  - resolve_book_decisions()
  - start_import_job()
  - get_job_status()
  - retry_failed_jobs()
  - pause_queue()
  - resume_queue()
- engine processing MUST be non-interactive and MUST survive restart via persisted job state.
- engine MAY provide a deterministic queue runner entrypoint (sync) to execute pending import jobs.

Import foundation MAY include a "hybrid" mode in the data model only. Behavior is reserved.

### 8.4 CLI Import Command (AM1-like)

The CLI MUST expose an AM1-like import entrypoint:

- Command: `audiomason import`
- The command MUST be implemented as a plugin-provided CLI command via `ICLICommands`.
- The providing built-in plugin MUST be named `import_cli`.

Behavioral requirements:

- The command MUST use the Import foundation and engine services under `plugins/import/`.
- PHASE 0 (preflight) MUST be deterministic and read-only.
- PHASE 1 MUST collect all decisions (interactive prompts unless explicitly disabled).
- PHASE 2 MUST be implemented exclusively via persisted Jobs created by ImportEngineService.
- Non-interactive operation MUST be possible via explicit CLI flags.

CLI import UX stability requirements:

- Interactive selection MUST NOT silently exit when an author has no books.
  The CLI must re-prompt or emit an explicit message before returning.
- The CLI MUST support mixed inbox layouts from import preflight:
  - author/book directories
  - single-level book directories
  - single-file units (archives/audio files)
- When debug verbosity is enabled (`-d` / `--debug`), the CLI MUST surface
  import-related runtime diagnostics envelopes on stdout.
- In non-interactive mode, unresolved selection/policy MUST fail loudly
  (non-zero exit) rather than silently returning.

## 9. Web Interface Rules

- Web interface is **UI only**.
- No business logic.
- No parallel sources of truth.
- No direct filesystem manipulation outside APIs.

The web UI must be replaceable without touching core logic.

### 9.0 Web server shutdown output (CLI contract)

When running the web server via the CLI (for example, `audiomason web`), the CLI MUST
emit exactly one shutdown summary line on process exit, in the following canonical form:

- Ctrl+C: `Finished (reason: interrupted by user)` with exit code 130
- Error: `Finished (reason: error: <TypeName>: <message>)` with exit code 1
- Normal return: `Finished (reason: normal exit)` with exit code 0

The literal line `Interrupted.` MUST NOT be printed.

### 9.0.1 Web server quiet mode output (CLI contract)

When running the web server in quiet mode (`audiomason -q web`), console output MUST be
exactly 2 lines and nothing else:

1) `Starting web server on port 8080...`
2) `Finished (reason: <...>)`

In quiet mode, uvicorn logging MUST be silenced (no startup/shutdown/access output).
Uvicorn log settings MUST map from AM verbosity as follows:

- QUIET: log_level=error, access_log=False
- NORMAL: log_level=info, access_log=False
- VERBOSE: log_level=info, access_log=True
- DEBUG: log_level=debug, access_log=True

### 9.1 Web Interface Configuration Surface

The web interface exposes a **UI-only** configuration surface. It must not create a
new source of truth; it only reads and writes through existing APIs.

Runtime configuration hooks:

- Config API contract:
  - `GET /api/am/config` returns:
    - `config` (nested config object)
    - `effective_snapshot` (object mapping `key_path` -> `{ value, source }`)
  - `POST /api/am/config/set` sets a single `key_path` in user config.
  - `POST /api/am/config/unset` unsets a single `key_path` in user config (reset to inherit).
  - Errors from config set/unset must be returned as ASCII-only text.

- Web config UI contract:
  - Basic configuration: fixed list of common keys (UI hardcoded list).
  - Advanced configuration: full-surface editor over all `effective_snapshot` entries.
  - Advanced supports an 'overrides only' view where `source == "user_config"`.
  - UI does not validate semantics; it only attempts `JSON.parse()` and falls back to a string.

- Common keys:
  - `web.host`, `web.port`: bind host/port for the HTTP server.
  - `web.upload_dir`: temporary upload directory used by the web server.
  - `inbox_dir`, `outbox_dir`, `stage_dir`: core filesystem roots shown/used by UI.
  - `logging.level`: canonical logging verbosity (resolved by resolver).
  - `ui.*`: UI theming and UI-related values (project-defined).
- UI overrides file:
  - Stored at `~/.config/audiomason/web_interface_ui.json`.
  - Shape: `{ "nav": [...], "pages": { ... } }`.
  - Read/write via `/api/ui/config`.
- Environment variables:
  - `WEB_INTERFACE_DEBUG`: enable extra diagnostic fields in API responses (also enabled when CLI verbosity is "debug").
  - `WEB_INTERFACE_STAGE_DIR`: override the stage upload directory.

Logs UI:

- The web server MUST NOT tail a web-specific log file as its primary diagnostics source.
- `/api/logs/stream` and `/api/logs/tail` stream recent diagnostics/events from the Core EventBus tap.
- When runtime diagnostics are enabled (`diagnostics.enabled`), Core also writes JSONL at `<stage_dir>/diagnostics/diagnostics.jsonl` and the web may expose it via file IO endpoints.

Developer endpoints:

- `/api/ui/schema`: returns the current default UI schema and the configuration hooks above.

### 9.2 Root browsing and "Run wizard here"

The web UI may browse only an allowlisted set of file roots exposed by the backend.

- The backend MUST expose `GET /api/roots`.
- The response MUST include only user-facing roots: `inbox`, `stage`, `jobs`, `outbox`.
- The `jobs` root may be hidden via config key `web_interface.browse.show_jobs_root` (default: true).
- Path traversal MUST be rejected (no `..` segments) in all file browsing and wizard-target inputs.

When creating a wizard job from the web UI, the selected filesystem target MUST be propagated into the wizard execution context:

- For each wizard execution target, orchestration MUST create a `ProcessingContext` with `source=<target_path>`.
- Batch mode is permitted: a single wizard job may execute the same wizard for multiple targets in a deterministic order.

Implementation note (web job creation):

- When the web backend creates a wizard job for a selected target, it MUST ensure the wizard payload contains a non-empty `source_path`.
- If the UI request omits `source_path` or provides an empty string, the backend MUST set `source_path` to the selected `target_path` before the job is queued.
- If the UI provides a non-empty `source_path`, the backend MUST NOT overwrite it.


Wizard listing contract:

- `/api/wizards` returns `items[]` where each item contains:
  - `name` (required)
  - `step_count` (optional)
  - `display_name` (optional)
  - `description` (optional)


### 9.2.1 Wizard Visual Configuration Editor

The web interface MUST allow editing wizard definitions visually (no YAML editing required):

- Reorder steps via drag & drop.
- Enable/disable steps (`step.enabled: bool`, default true).
- Edit per-step defaults (stored under `step.defaults` as a mapping).
- Step templates and defaults-memory are stored under a single, explicit UI namespace:
  - `wizard._ui.defaults_memory` (mapping)
  - `wizard._ui.templates` (mapping: template_name -> step partial mapping)

Rules:

- Wizard YAML remains the single source of truth and is saved only via WizardService.
- The UI MUST use the model-based API (`PUT /api/wizards/{name}` with `model`).
- The backend MUST perform server-side validation before saving:
  - Reject duplicate step ids.
  - Reject non-mapping steps.
  - Enforce JSON/YAML-like structures for `defaults` and `when`.

Backend API additions:

- `POST /api/wizards/validate` with body `{yaml?: str, model?: object}`.
  - Returns `{ok: true, yaml: str, model: object}` on success.
  - Returns HTTP 400 with error detail on invalid input.

The editor may store future-facing condition data under `step.when` without requiring runtime support.


---

### 9.3 Web Import Wizard UX

The web interface MUST expose a dedicated Import Wizard UX that mirrors the
guided author -> book selection flow from AM1.

Rules:

- The web interface MUST NOT implement import logic.
- All import detection and job creation MUST be delegated to the Import plugin
  services (plugins/import/), which are the single source of truth.
- The UX MUST be a simple guided flow:
  - Select the source root/path.
  - Select an author (auto-next to books).
  - Select a book (auto-start).
- The UI MUST show a minimal async indicator while API calls are running.

Backend API contract:

- Preflight listing:
  - `GET /api/import_wizard/preflight?root=<root>&path=<rel_path>`
  - Returns `authors[]` and `books[]` (each book includes `rel_path`).
- Start import processing for a selected book:
  - `POST /api/import_wizard/start` with JSON body:
    - `root` (required)
    - `path` (optional, default: ".")
    - `book_rel_path` (required)
    - `mode` (optional: stage|inplace|hybrid, default: stage)
  - The backend MUST create persisted import Jobs via ImportEngineService.
- Queue runner hook (optional, for web-triggered execution):
  - `POST /api/import_wizard/run_pending` with JSON body `{ "limit": <n> }`.

The UI MAY offer a manual "run pending" trigger using the endpoint above.

---

### 9.4 Web File Management API

The web interface provides a UI surface for filesystem operations, but it MUST NOT implement filesystem logic itself.
All filesystem operations MUST be delegated to the File I/O Capability (file_io plugin / FileService).

Requirements:
- All operations are restricted to configured roots (jail): inbox, stage, jobs, outbox.
- Directory listings must be stable-ordered (deterministic).
- Upload supports:
  - file upload (including .rar as a regular file),
  - directory upload as a directory tree (relative paths preserved).
- Download supports:
  - file download (streamed),
  - directory download either as a bulk set of file downloads or as a streamed archive (zip or tar).
- File names in inbox may contain non-ASCII characters; the UI/API must preserve them as UTF-8 and MUST NOT apply ASCII sanitization.


## 10. Logging & Observability

Observability in AudioMason2 consists of two mandatory and distinct layers:

1) Human-readable logging (core logger based)
2) Structured runtime diagnostic events (authoritative diagnostic emission entry point)

These layers are complementary and non-substitutable.

---

### 10.1 Human-Readable Logging (Mandatory)

Human-readable logs MUST go through the Core-provided logger.

Plugins, Jobs, Wizards, CLI and Web layers:

- MUST NOT use print() for runtime logging.
- MUST NOT use stdlib logging directly.
- MUST use the Core-provided logger exclusively.

Minimum logging requirement:

Any component that performs work or participates in a call boundary MUST log:

- start of the operation,
- end of the operation (succeeded or failed).

Logs MUST be deterministic, concise, and suitable for human debugging.

Logging does NOT substitute structured diagnostic event emission.

---

### 10.2 Structured Runtime Diagnostic Events (Mandatory)

Authoritative diagnostic emission entry point:

audiomason.core.events.get_event_bus().publish(event, data)

Async variant:

audiomason.core.events.get_event_bus().publish_async(event, data)

All structured runtime diagnostic lifecycle and call-boundary events MUST be emitted exclusively via the above entry point.

Forbidden:

- Direct instantiation of EventBus for diagnostic emission.
- Creating alternate diagnostic emission paths or global buses.
- Bypassing audiomason.core.events.get_event_bus() for emission.

Minimum emission requirement:

Any component that performs work or participates in a call boundary MUST:

- emit a start event,
- emit a terminal event (succeeded or failed).

Failure handling rule:

- Errors MUST NOT be silently swallowed.
- If an invoked component fails, the invoking component MUST emit a failure diagnostic event preserving sufficient context to identify:
  - the component or operation,
  - the boundary invocation,
  - and the failure reason (minimum: error type and message).

Non-substitution rule:

- Logging, exceptions, or return values do NOT substitute mandatory diagnostic event emission.

Fail-safe requirement:

- Failure of the diagnostic emission mechanism MUST NOT crash or block processing.


### 10.3 Runtime Diagnostics (Envelope + JSONL Sink)

The runtime diagnostics layer has a canonical envelope schema and a central JSONL sink.

Envelope schema (mandatory):

- "event": string
- "component": string
- "operation": string
- "timestamp": ISO8601 UTC string ending with "Z" (example: 2026-02-11T12:34:56Z)
- "data": object (JSON dict)

No keys outside this schema are allowed for envelope events.

Enablement key (canonical):

- diagnostics.enabled

Enablement sources and priority (mandatory):

1) CLI args
2) ENV: AUDIOMASON_DIAGNOSTICS_ENABLED
3) config files
4) defaults (disabled)

ENV values are strings and are normalized as:

- true: "1", "true", "yes", "on" (case-insensitive)
- false: "0", "false", "no", "off" (case-insensitive)

Unknown values MUST be treated as disabled.

Examples (mandatory):

Config:

diagnostics:
  enabled: true

ENV:

export AUDIOMASON_DIAGNOSTICS_ENABLED=1

CLI:

audiomason process book.m4a --diagnostics
audiomason process book.m4a --no-diagnostics

Diagnostics console (CLI plugin):

- audiomason diag [--mode events|log|both]
- audiomason diag tail [--max-events N] [--no-follow] [--mode events|log|both]
- audiomason diag status
- audiomason diag on
- audiomason diag off

Diagnostics console config:

- diagnostics.console.wait_status_repeat: bool (default false)
  - false: print waiting status once
  - true: repeat waiting status periodically

JSONL sink (mandatory):

- The sink MUST be registered once per process and MUST receive ALL published events.
- A CLI diagnostics console may tail this sink to provide live visibility; this must not change emission semantics.
- Implementation MUST use EventBus.subscribe_all(callback).
- Sink path (append-only): <stage_dir>/diagnostics/diagnostics.jsonl
- The sink MUST be installed unconditionally; disabled mode means no writes.
- When diagnostics are disabled, the sink MUST perform no file IO.
- When enabled, the sink MUST append exactly one JSON object per published event.
  - If the event payload is already the canonical envelope, write it as-is.
  - Otherwise, wrap it into the envelope using component="unknown" and operation="unknown".

Fail-safe requirement:

- Any sink write failure MUST be caught and logged as warning; it MUST NOT crash runtime.


### 10.4 Runtime Diagnostics Event Set (Mandatory)

All events below MUST be published via EventBus using the canonical envelope schema.
The EventBus event name MUST equal the envelope "event" value.

Required status values:
- "running" for start events
- "succeeded" / "failed" / "cancelled" for terminal events

Required events (minimum):

Orchestration (component="orchestration")
- diag.job.start
  - operation: "run_job"
  - data: {job_id, job_type, status}
- diag.job.end
  - operation: "run_job"
  - data: {job_id, job_type, status, duration_ms, error_type?, error_message?}
- diag.ctx.start
  - operation: "context_lifecycle"
  - data: {job_id, context_index, context_total, source}
- diag.ctx.end
  - operation: "context_lifecycle"
  - data: {job_id, context_index, context_total, source, status}
- diag.boundary.start
  - operation: "execute_pipeline" or "run_wizard"
  - data: {job_id, pipeline_path?/wizard_id?, source}
- diag.boundary.end
  - operation: "execute_pipeline" or "run_wizard"
  - data: {job_id, pipeline_path?/wizard_id?, source, status, error_type?, error_message?}
- diag.boundary.fail
  - operation: "execute_pipeline" / "run_wizard" / "plugin_call"
  - data: {job_id?, pipeline_path?/wizard_id?/step_id?, error_type, error_message}

Pipeline (component="pipeline")
- diag.pipeline.start
  - operation: "execute_from_yaml"
  - data: {pipeline_path, source, status}
- diag.pipeline.end
  - operation: "execute_from_yaml"
  - data: {pipeline_path, source, status, duration_ms, error_type?, error_message?}
- diag.pipeline.step.start
  - operation: "step"
  - data: {step_id, plugin, interface, source}
- diag.pipeline.step.end
  - operation: "step"
  - data: {step_id, plugin, interface, source, status, duration_ms, error_type?, error_message?}

Wizard (component="wizard")
- diag.wizard.start
  - operation: "run_wizard"
  - data: {wizard_id, step_count, source, status}
- diag.wizard.end
  - operation: "run_wizard"
  - data: {wizard_id, status, duration_ms, error_type?, error_message?}

Compatibility rule:
- Existing event names may continue to be emitted (e.g. diag.wizard.run.*) but MUST also use the canonical envelope.


## 11. Testing Requirements

- MyPy strict typing is mandatory.
- Ruff must pass with zero warnings.
- Pytest coverage must remain high.
- New functionality must include tests.

Untested features are invalid features.

---


## 12. Documentation & Governance (MANDATORY)

### 12.1 Documentation Obligation (Creation **and Update**)

Every implementation **must**:

- deliver **new documentation** for any newly introduced behavior, API, or user-facing feature,
- **update existing documentation** if the implementation changes, extends, or invalidates it,
- ensure that no documentation becomes stale or misleading as a result of the change.

Adding code **without updating affected documentation is invalid**.

Documentation is not an optional artifact.
Documentation is part of the implementation contract.

---

### 12.2 Specification as Primary Source of Truth

This specification is the **primary and authoritative source of truth** for the entire project.

Consequences:

- If documentation conflicts with this specification, **the specification wins**.
- If code conflicts with this specification, **the code is invalid**.
- Existing documentation **must be updated** to reflect this specification where discrepancies exist.

No document, README, comment, or implementation may redefine behavior already specified here.

---

### 12.3 Mandatory Specification Updates

If an implementation changes behavior, architecture, contracts, or invariants:

- **this specification MUST be updated first or in the same change set**,
- the update must be explicit and reviewable,
- implementation without a corresponding specification update is invalid.

The specification defines the rules.
The code merely implements them.

---

### 12.4 Mandatory Implementation Plan

Before **any** non-trivial implementation:

- a **qualified implementation plan** must be provided,
- the plan must explain:
  - scope
  - affected components
  - phase impact
  - reversibility
  - risks
- implementation may start **only after approval**.

Skipping the plan phase is a violation of project rules.


## 13. Change Management Rules

- No "quick fixes".
- No silent behavior changes.
- No architectural shortcuts.

If a rule blocks progress:
-> update the specification first.

---

## 14. Authority

This document has higher authority than:

- individual commits
- patches
- chat discussions
- temporary workarounds

If something conflicts with this specification, the specification wins.

---

## 15. Closing Statement

AudioMason2 is a long?term project.

This specification exists to ensure that:
- progress is sustainable,
- mistakes are reversible,
- and the system does not collapse under its own complexity.

**Code follows specification, not the other way around.**
