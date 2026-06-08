# Import Plugin JSON-Orchestrated Flow Remediation Plan

## Goal

Bring the import plugin to a fully compliant state where WizardDefinition v3 JSON
and registered primitives are the only orchestration authority for PHASE 1 flow.
Remove hidden engine-side step semantics and helper-driven flow authority.

Execution must be strictly serial: one subbot stage at a time, no overlap.

## Constraints and Guardrails

- Enforce no hidden step logic: each flow-visible action must be an explicit
  `primitive_id@version` node in WizardDefinition v3.
- Enforce primitive registry authority: every used primitive must be declared in
  `primitive_registry.json` with valid metadata and schemas.
- Enforce zero new projection runtime policy: do not introduce any new Python
  projection runtime layer/module as a replacement for hidden helpers.
- Enforce business-logic migration: PHASE 1 business rules currently in
  `phase1_*` helpers must move into explicit JSON nodes plus declared primitive
  semantics.
- Preserve fixed prompt payload contracts:
  - `ui.prompt_select@1` -> `{"selection": <json>}`
  - `ui.prompt_text@1` -> `{"value": <json>}`
  - `ui.prompt_confirm@1` -> `{"confirmed": <bool>}`
- Keep execution deterministic and renderer-neutral.
- Keep PHASE 1 as discovery/validation/planning only; no PHASE 2 execution in
  interpreter path.
- Enforce strict serial execution: SB-00 -> SB-01 -> SB-02 -> SB-03 -> SB-04 ->
  SB-05 -> SB-06, with hard handoff gates between stages.
- Enforce no-drift policy: once a stage output is approved, downstream stages
  cannot silently change it without explicit rollback + re-approval.
- Treat repository tests as out of scope for this remediation run:
  - do not modify test files,
  - do not execute `pytest` manually,
  - do not delegate `pytest` execution to subbots.

## Primitive Granularity Guardrails (Hard Rule)

- Do not introduce catchall PHASE 1 primitives (`phase1.compute_all`,
  `phase1.refresh_all`, or equivalent single-step full projection rebuilds).
- Each primitive must have one atomic responsibility and bounded deterministic
  I/O.
- Primitive code must not branch on `step_id` or renderer-specific behavior.
- Primitive outputs must be data only; session mutation authority stays in JSON
  node `writes`.
- Runtime/network boundaries are allowed only where strictly required by the
  domain contract (for example metadata provider validation).
- If a proposed primitive replaces multiple helper modules at once, treat as
  FAIL and split into smaller primitives.

## Serial Execution Protocol (Hard Rule)

- Only one active stage at any time.
- A stage starts only after prior stage has:
  - documented outputs,
  - explicit acceptance criteria pass,
  - frozen artifact fingerprint(s) recorded.
- Any detected mismatch to frozen fingerprints is a hard stop.
- Recovery path is serial as well: rollback to the last valid freeze point,
  then rerun downstream stages in order.

## Anti-Drift Controls

- Freeze points:
  - FP-0: spec/compliance matrix
  - FP-1: hidden-logic inventory and operation-contract map
  - FP-2: primitive surface + registry snapshot
  - FP-3: WizardDefinition v3 graph snapshot
  - FP-4: engine detox diff snapshot
  - FP-5: helper-boundary snapshot
  - FP-6: conformance + gate report
- Drift checks at each handoff:
  - compare artifact fingerprints and expected step contracts,
  - reject undocumented semantic changes,
  - require explicit change note before continuing.

## Delegation Workstreams

### SB-00: Specification Gatekeeper

- Build a compliance matrix against the key rules for v3 DSL authority,
  primitive registry authority, and prompt payload contracts.
- Decide if new primitive semantics require specification updates.
- If yes, prepare a separate spec-first change before implementation.

### SB-01: Flow Forensics

- Inventory hidden orchestration in:
  - `plugins/import/phase1_source_intake.py`
  - `plugins/import/phase1_metadata_flow.py`
  - `plugins/import/phase1_cover_flow.py`
  - `plugins/import/phase1_policy_flow.py`
  - `plugins/import/engine_step_submit.py`
  - `plugins/import/engine_session_create.py`
  - `plugins/import/engine_processing.py`
  - `plugins/import/engine.py`
- Produce a mapping from current helper behavior to explicit primitive
  operation contracts (inputs, outputs, writes, and error behavior).

### SB-02: Primitive Architecture

- Define small deterministic primitives for all currently hidden PHASE 1 logic.
- Remove pseudo-primitives and no-op orchestration nodes as authorities.
- Add strict `inputs_schema` and `outputs_schema` for each primitive.
- Register all required primitives through the existing registry model/storage.
- Attach a per-primitive contract note proving atomic scope and explicit non-
  overlap with other primitives.

### SB-03: WizardDefinition v3 Rewrite

- Refactor `plugins/import/dsl/default_wizard_v3_source.json` so orchestration
  is explicit in node graph and writes.
- Replace placeholder/no-op orchestration nodes with meaningful primitive steps.
- Encode PHASE 1 business rules directly in node graph/writes/guards so they do
  not depend on `phase1_*` helper orchestration.
- Keep entry and terminal constraints unchanged (`select_authors` and
  `processing`).

### SB-04: Engine Detox

- Remove engine-side orchestration hooks that mutate flow authority outside DSL,
  including:
  - post-submit loop synchronization helpers,
  - hidden PHASE 1 projection recomputation used as flow authority,
  - step-id-specific orchestration behavior outside interpreter semantics.
- Ensure `run_automatic_steps` + explicit submit path are the only transition
  authority for v3 sessions.

### SB-05: Helper Sunset, Bridge Removal, and File Deletion

- Remove `import.phase1_refresh` bridge authority and any call path that uses
  helper-driven projection recomputation as runtime authority.
- Delete helper modules after migration is complete:
  - `plugins/import/phase1_cover_flow.py`
  - `plugins/import/phase1_metadata_flow.py`
  - `plugins/import/phase1_policy_flow.py`
  - `plugins/import/phase1_source_intake.py`
- Ensure no runtime import references remain to these files in plugin/engine/
  plan/primitive execution paths.
- Verify that helper behavior was split across multiple atomic JSON-driven
  primitives, not re-centralized into one replacement primitive.

#### SB-05 Spec Gate Status (Rules 648, 650-657)

- Current status for `RULE.ARCH.IMPORT_V3_PHASE1_OPERATIONS_MUST_BE_PRIMITIVE_REGISTRY_DECLARED`
  is FAIL until `import.phase1_refresh` bridge authority is fully removed from:
  - `plugins/import/dsl/default_wizard_v3_source.json`
  - `plugins/import/wizard_callable_manifest.json`
  - `plugins/import/plugin.yaml`
  - `plugins/import/plugin.py`
  - `plugins/import/primitives/call_v1.py`
- During migration, preserve parity obligations from rules 650-657 as hard
  acceptance constraints, especially:
  - per-book post-edit metadata authority (no first-book collapse),
  - concrete per-book cover authority,
  - independent skip_processed_books axis,
  - deterministic two-pass ordering.

### SB-06: Verification and Conformance

- Verify conformance without test updates and without `pytest` execution:
  - no hidden orchestration authority remains,
  - all v3 nodes reference declared primitives,
  - prompt payload contracts are strictly enforced,
  - deterministic replay traces only explicit DSL steps.
- Use non-pytest checks and artifact inspection for this run, including:
  - import/reference scans proving deleted helper modules are no longer used,
  - primitive and node contract inspection for PHASE 1 transitions,
  - lint/type checks on changed implementation files only.

## Delivery Sequence

1. SB-00 only: spec/compliance gate. Freeze FP-0.
2. SB-01 only: flow forensics and mapping. Freeze FP-1.
3. SB-02 only: primitives and registry. Freeze FP-2.
4. SB-03 only: WizardDefinition v3 rewrite. Freeze FP-3.
5. SB-04 only: engine detox. Freeze FP-4.
6. SB-05 only: helper sunset. Freeze FP-5.
7. SB-06 only: verification and conformance. Freeze FP-6.
8. Final integration closure for this run without `pytest`/Amp.

## Definition of Done

- No hidden PHASE 1 orchestration remains in engine/session submit paths.
- Every flow-visible PHASE 1 operation is an explicit v3 node with declared
  primitive metadata.
- No PHASE 1 projection/runtime business logic remains in Python helper modules
  outside primitive semantics.
- New primitive surface remains atomic and non-catchall under the granularity
  guardrails.
- `RULE.ARCH.IMPORT_V3_PHASE1_OPERATIONS_MUST_BE_PRIMITIVE_REGISTRY_DECLARED`
  is satisfied with no remaining `import.phase1_refresh` bridge authority.
- No runtime references remain to:
  - `plugins/import/phase1_cover_flow.py`
  - `plugins/import/phase1_metadata_flow.py`
  - `plugins/import/phase1_policy_flow.py`
  - `plugins/import/phase1_source_intake.py`
- Prompt payload keys are strict and spec-compliant.
- Replay and runtime traces are deterministic and show only explicit DSL-driven
  behavior.
- Test-suite updates and `pytest` execution remain explicitly out of scope for
  this remediation run.
