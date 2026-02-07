
# AudioMason2 – Project Specification (Authoritative)

Author: Michal Holeš  
Status: **AUTHORITATIVE / BINDING**  
Applies to: AudioMason2 core, plugins, tooling, UI, tests, documentation  
Language: **English (mandatory for all repository content)**

---

## 1. Purpose of This Document

This document is the **authoritative specification** for the AudioMason2 (AM2) project.

Its role is to:

- define **what AudioMason2 is and must be**,
- establish **non‑negotiable architectural and behavioral rules**,
- act as a **binding contract** for all future development,
- prevent architectural drift, monolith growth, and ad‑hoc fixes,
- ensure long‑term maintainability, testability, and extensibility.

Any implementation, patch, refactor, or feature **must comply with this specification**.

If a change contradicts this document, the change is **invalid** unless the specification itself is updated and approved first.

---

## 2. Core Vision

AudioMason2 is a **general‑purpose, plugin‑driven, asynchronous media processing platform** with a strong focus on:

- audiobooks (primary use case),
- deterministic behavior,
- user‑controlled workflows,
- extensibility through plugins,
- multiple user interfaces (CLI, Web, Daemon),
- long‑term evolvability without rewrites.

AM2 is not a collection of scripts.  
AM2 is an **engine + ecosystem**.

---

## 3. Fundamental Principles (Non‑Negotiable)

### 3.1 Ultra‑Minimal Core

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

### 3.2 Plugin‑First Architecture

- Plugins are the primary extension mechanism.
- Core depends on **interfaces**, never concrete implementations.
- Plugins may add, modify, or disable behavior.
- Plugins must be isolatable and removable without breaking the system.

No feature may be added directly to core if it can exist as a plugin.

---

### 3.3 Deterministic Behavior

- Same inputs + same config = same outputs.
- No hidden state.
- No time‑dependent logic unless explicitly modeled.
- All behavior must be observable via logs and job state.

---

### 3.4 Asynchronous by Design

- Long‑running operations must be asynchronous.
- UI must never block on processing.
- Progress and logs must be observable while work is running.

Synchronous shortcuts are forbidden except for trivial operations.

---

## 4. Execution Model (Strict Contract)

### 4.1 Three‑Phase Model

All processing follows **exactly** these phases:

1. **PHASE 0 – Preflight**
   - Detection only
   - Read‑only
   - No side effects
   - No user interaction

2. **PHASE 1 – User Input**
   - Interactive
   - UI‑controlled (CLI/Web)
   - All decisions are collected here

3. **PHASE 2 – Processing**
   - **STRICTLY NON‑INTERACTIVE**
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
- progress (0.0–1.0)
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
- User‑installed plugins live in user plugin directories only.
- Installation mechanism must be abstracted.

---

## 8. Wizard System

### 8.1 Wizard Service

- All wizard access goes through **WizardService API**.
- UI must not manipulate wizard files directly.

---

### 8.2 Wizard Execution

- Wizard execution produces jobs.
- Wizard UI interaction happens only in PHASE 1.
- Processing follows standard pipeline rules.

---

## 9. Web Interface Rules

- Web interface is **UI only**.
- No business logic.
- No parallel sources of truth.
- No direct filesystem manipulation outside APIs.

The web UI must be replaceable without touching core logic.

---

## 10. Logging & Observability

- Logging is job‑centric.
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

- No “quick fixes”.
- No silent behavior changes.
- No architectural shortcuts.

If a rule blocks progress:
→ update the specification first.

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

AudioMason2 is a long‑term project.

This specification exists to ensure that:
- progress is sustainable,
- mistakes are reversible,
- and the system does not collapse under its own complexity.

**Code follows specification, not the other way around.**
