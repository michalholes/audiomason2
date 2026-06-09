2026-06-09T00:15:00Z added an interactive prompt when the runtime wizard definition drifts from the shipped default.

- The import launcher now compares the runtime `wizards/import/definitions/wizard_definition.json` against the shipped default wizard JSON.
- When they differ, the user is asked whether to delete the runtime artifact and regenerate the shipped default on the next load.
- The prompt is skipped when the runtime already matches the default or when import runs noninteractively.
