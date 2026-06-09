2026-06-09T00:00:00Z made the import launcher auto-accept valid default root/path values.

- Interactive launcher now returns the configured default root and relative path without prompting when defaults validate.
- This removes the redundant inbox selection and blank path confirmation from the start of the import flow.
- Explicit CLI overrides and fixed/noninteractive modes remain unchanged.
