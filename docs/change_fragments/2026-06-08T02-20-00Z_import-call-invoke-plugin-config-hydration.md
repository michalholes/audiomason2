2026-06-08T02:20:00Z made call.invoke hydrate plugin config before callable execution.

- Updated `plugins/import/primitives/call_v1.py` to load plugin config via `PluginRegistry` for the resolved plugin id.
- If plugin exposes `configure(config)`, call.invoke now applies the resolved config before invoking the published callable.
- This removes silent default-config execution for job callables and keeps JSON-orchestrated call.invoke behavior aligned with configured plugin runtime settings.
