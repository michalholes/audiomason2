2026-06-08T00:05:00Z removed unused `source.build_catalog` primitive from import runtime.

- Removed `source.build_catalog` from source primitive registry entries.
- Removed `source.build_catalog` dispatch from `plugins/import/primitives/__init__.py`.
- Deleted the `source.build_catalog` implementation path from `plugins/import/primitives/source_v1.py`.
