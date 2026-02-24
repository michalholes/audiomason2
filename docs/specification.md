# AudioMason2 - Project Specification (Overview)

Specification Version: 1.1.24

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
