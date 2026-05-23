# Lessons Learned

## 2026-05-22

### Optimization 1: Cluster-first strict cleanup for Any-heavy areas
- impact: Material reduction in iteration count by fixing high-error clusters in one pass instead of file-by-file hopping.
- affected workflow step or files: `plugins/web_interface/**`, then remaining top offenders (`plugins/example_plugin/plugin.py`, `plugins/diagnostics_console/plugin.py`, `plugins/syslog/*`).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 2: Route registration pattern to avoid decorator-induced Any
- impact: Removed repeated typing failures and reduced rework by standardizing on `app.add_api_route(...)` where strict typing around decorators produced `Any` leakage.
- affected workflow step or files: web API modules under `plugins/web_interface/api/*.py`, plus `plugins/web_interface/ui_static.py` and `plugins/web_interface/core.py` endpoints.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 3: Typed boundary helpers for request/app state and JSON parsing
- impact: Faster convergence to strict green by reusing small typed helpers instead of ad-hoc casts in each endpoint.
- affected workflow step or files: `_StateView` protocols, `request.state` accessors, `Mapping`-to-`dict[str, object]` normalizers, `json_loads_object` boundary usage.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 4: Prefer callable cache objects over `lru_cache` in strict no-`Any` zones
- impact: Preserved `cache_clear()` test contracts while avoiding `functools.lru_cache` typing leakage (`Callable[..., Any]`) under strict anti-`Any` policy.
- affected workflow step or files: `plugins/metadata_openlibrary/plugin.py`, `plugins/import/metadata_boundary.py`, `plugins/import/phase1_metadata_flow.py`.
- safety class: instruction-only
- scope: inside current issue scope
