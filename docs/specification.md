
# AudioMason2 - Project Specification (Authoritative)

Specification Version: 1.0.5
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
- Every change to this specification MUST increment the patch number by +1 (e.g., 1.0.0 -> 1.0.1).
- Every change delivered by a patch MUST be recorded in docs/changes.md.
- Each change entry in docs/changes.md MUST start with an ISO 8601 timestamp captured at patch creation time.

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

#### 7.4.2 Operations

The capability must provide, at minimum:

- list_dir (stable deterministic order)
- stat
- exists
- open_read (download streaming)
- open_write (upload streaming)
- mkdir (parents supported)
- rename (move)
- delete_file
- rmdir (empty directories only)
- rmtree (recursive delete)
- copy
- checksum (sha256 default)

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

## 9. Web Interface Rules

- Web interface is **UI only**.
- No business logic.
- No parallel sources of truth.
- No direct filesystem manipulation outside APIs.

The web UI must be replaceable without touching core logic.

### 9.1 Web Interface Configuration Surface

The web interface exposes a **UI-only** configuration surface. It must not create a
new source of truth; it only reads and writes through existing APIs.

Runtime configuration hooks:

- Config keys (via `/api/am/config` and `/api/am/config/set`):
  - `web.host`, `web.port`: bind host/port for the HTTP server.
  - `web.upload_dir`: temporary upload directory used by the web server.
  - `inbox_dir`, `outbox_dir`, `stage_dir`: core filesystem roots shown/used by UI.
  - `ui.*`: UI theming and UI-related values (project-defined).
- UI overrides file:
  - Stored at `~/.config/audiomason/web_interface_ui.json`.
  - Shape: `{ "nav": [...], "pages": { ... } }`.
  - Read/write via `/api/ui/config`.
- Environment variables:
  - `WEB_INTERFACE_DEBUG`: enable extra diagnostic fields in API responses (also enabled when CLI verbosity is "debug").
  - `WEB_INTERFACE_STAGE_DIR`: override the stage upload directory.
  - `WEB_INTERFACE_LOG_PATH`: optional log file path used for server log tail/stream.

Developer endpoints:

- `/api/ui/schema`: returns the current default UI schema and the configuration hooks above.

Wizard listing contract:

- `/api/wizards` returns `items[]` where each item contains:
  - `name` (required)
  - `step_count` (optional)
  - `display_name` (optional)
  - `description` (optional)

---

### 9.2 Web File Management API

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

- Logging is job?centric.
- All logs are attributable to a job_id.
- Verbosity levels must be respected globally.

Silent failures are forbidden.

---

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
