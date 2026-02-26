# AudioMason2 - Project Specification (Overview)

Specification Version: 1.1.31
This file is an overview entrypoint only.

Normative authority:
- The only authoritative specification is the layered set under docs/spec/.
- Entry point: docs/spec/00_index.md
- Layers:
  - ARCH: docs/spec/10_architecture.md
  - WIRE: docs/spec/20_wire_contracts.md
  - LAYOUT: docs/spec/30_implementation_bindings.md

This file is non-normative. If there is any conflict, docs/spec/00_index.md and
the layer precedence rules apply.

Notes:
- Issue 238 extends the import CLI editor with explicit FlowConfig and
  WizardDefinition editor areas.

- Issue 240 extends the import plugin Web UI with FlowConfig and WizardDefinition
  editors (tabs), backed by strict wrapper contracts, validate-only endpoints,
  and deterministic history/rollback behavior.

- Issue 259 refactors the Flow Editor layout from an overlay model into a
  deterministic grid-based sidebar with explicit tabs.

- Issue 264 further consolidates the Flow Editor into a single authoritative
  layout with deterministic sidebar sections (details, transitions, palette),
  and tightens runtime validation for FlowGraph and behavioral step metadata.

- Issue 265 completes the Flow Editor correction: transitions use a visual
  condition builder (no raw JSON), step details render full behavioral
  semantics, the palette shows extended metadata, unified config mode no longer
  mirrors JSON per keystroke, and Save gating is centralized in FlowEditorState.

- Issue 267 refines Flow Editor row UX: click selects, explicit drag handle grip, and simplified row actions.

- Issue 268 eliminates remaining Flow Editor deficiencies: WizardDefinition v1 migration,
  enforced v2 canonical storage/serving, and deterministic icon/CSS wiring.
