# Change Fragment

- activated `import.phase1_runtime` in `plugins/import/primitives/__init__.py`
- routed non-interactive execution through the primitive boundary instead of interpreter fallback activation
- removed duplicate registry/bootstrap activation outside the primitive boundary
