
# AUDIOMASON2_PROJECT_CONTRACT.md
Version: 1.1

Status: AUTHORITATIVE / IMMUTABLE BASE CONTRACT  
Applies to: Entire AudioMason2 project (core, plugins, UI, tests, tooling, docs)  
Language: ENGLISH ONLY (ASCII ONLY)  
Update policy: DO NOT UPDATE (superseded only by explicit successor contract)

---

## 1. Purpose of This Contract

This document defines the foundational, non-expiring contract of the AudioMason2 project.

It exists to:

- define the irreducible invariants of the project,
- prevent architectural drift over time,
- serve as a permanent reference point for all future specifications,
- outlive implementations, refactors, rewrites, and partial failures.

This contract is intentionally minimal and must not require regular updates.

More detailed or evolving rules belong in:
- the Project Specification,
- implementation plans,
- documentation.

If any document or code contradicts this contract, the contract wins.

---

## 2. Language, Encoding, and Repository Rules

- All repository content MUST be written in English.
- All authoritative documents MUST be ASCII-only.
- Non-ASCII characters are forbidden in:
  - specifications
  - contracts
  - documentation
  - source code comments
  - commit messages

---

## 3. Core Identity of AudioMason2

AudioMason2 is:

- a general-purpose media processing engine,
- plugin-driven by design,
- asynchronous-first,
- deterministic and testable,
- UI-agnostic,
- designed for long-term evolution without rewrites.

AudioMason2 is NOT:

- a collection of scripts,
- a single-purpose audiobook tool,
- a monolithic application,
- a UI-centric system.

---

## 4. Non-Negotiable Architectural Invariants

### 4.1 Ultra-Minimal Core

- Core contains infrastructure only.
- Core never implements business logic.
- Core never implements UI.
- Core never implements storage backends.
- Everything beyond infrastructure is a plugin.

### 4.2 Plugin-First World

- Plugins are the primary extension mechanism.
- Core depends only on interfaces.
- No feature may be added to core if it can exist as a plugin.

### 4.3 Deterministic Behavior

- Same inputs plus same configuration produce same outputs.
- No hidden state.
- No implicit side effects.

### 4.4 Asynchronous Execution

- Long-running work is asynchronous.
- UI never blocks on processing.
- Progress and logs are observable.

---

## 5. Execution Contract

### 5.1 Three-Phase Model

All work follows exactly these phases:

- PHASE 0: Preflight (detection only, read-only)
- PHASE 1: User Input (interactive, UI-owned)
- PHASE 2: Processing (strictly non-interactive)

Any violation of phase boundaries is a contract violation.

### 5.2 Jobs as the Only Execution Unit

- Every operation that does work is a Job.
- UI may only create, observe, or cancel Jobs.
- UI may never execute processing directly.

---

## 6. Configuration Contract

- All runtime configuration access goes through a resolver API.
- No component reads configuration files directly.
- Configuration priority is fixed and global.

---

## 7. Plugin Contract

- There is exactly one source of truth for plugin state.
- Plugin failure must not crash the system.
- Plugins must not assume filesystem layout.

---

## 8. Wizard Contract

- Wizards are user-facing configuration flows.
- Wizards never perform processing directly.
- Wizard execution produces Jobs.

---

## 9. UI Contract

- UI layers are thin and replaceable.
- UI contains no business logic.
- UI never mutates repository state.

---

## 10. Documentation and Governance Contract

### 10.1 Documentation Obligation

Every implementation MUST:

- add documentation for new behavior,
- update existing documentation when behavior changes,
- update specifications if contracts change.

Code without updated documentation is invalid.

### 10.2 Specification Authority

- Specifications derive authority from this contract.
- Specifications may evolve.
- This contract does not.

---

## 11. Implementation Discipline

- No non-trivial code without an approved implementation plan.
- Plans must explain scope, impact, reversibility, and risks.
- Skipping the planning step is a violation.

---

## 12. Final Authority

This contract has higher authority than:

- specifications
- code
- tests
- documentation
- discussions

If something conflicts with this document, this document wins.

---

END OF CONTRACT
