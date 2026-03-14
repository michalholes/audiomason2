2026-03-13T22:48:10Z

Add Flow Editor JSON modal entry points for WizardDefinition and FlowConfig drafts,
with shared clipboard handling, modal actions for save and apply, and UI/tests
for future-run draft editing.
Keep the browser modal helper globals behind local typed aliases and hoist save/apply status locals for JS lint and type-check safety.
