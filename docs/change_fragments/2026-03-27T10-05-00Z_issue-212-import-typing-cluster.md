# Issue 212 repair: import typing cluster cleanup

## What changed
- tightened the import prompt/runtime typing surface in `import_wizard_v3.js`
- normalized wizard definition editor typing around stable graph and v2 draft replacement
- typed the wizard table and transition renderers against the authoritative import UI contracts
- extended `types/am2-import-ui-globals.d.ts` with authoritative wizard-definition graph and transition shapes used by the repaired UI assets

## Why
The issue 212 overlay still left a large TypeScript failure cluster inside the import UI asset set. This repair removes the remaining import-cluster TypeScript debt without touching `tsconfig*`.

## Validation
- repo-wide TypeScript errors on the authoritative overlay dropped from 462 to 187
- issue-212 import-cluster TypeScript errors for
  - `import_wizard_v3.js`
  - `wizard_definition_editor.js`
  - `wd_table_render.js`
  - `wd_transitions_render.js`
  dropped from 275 to 0
