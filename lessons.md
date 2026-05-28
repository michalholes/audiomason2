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

## 2026-05-23

### Optimization 5: Public engine boundary wrappers before strict cross-module cleanup
- impact: Materially reduced `reportPrivateUsage` churn by centralizing class-internal access through explicit public wrappers, then switching satellite modules in one pass.
- affected workflow step or files: `plugins/import/engine.py` wrapper surface first, then dependent modules (`engine_processing.py`, `engine_session_create.py`, `engine_step_submit.py`, `flow_config_*`, API boundaries).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 6: Shared mapping normalizer for strict `reportUnknown*` hotspots
- impact: Reduced multi-file strict churn by fixing `Mapping[Unknown, Unknown]` at boundaries once (`cast(Mapping[object, object], value)` + reusable normalizer), preventing repeated key/value unknown cascades.
- affected workflow step or files: helper blocks like `_dict_str_object(...)` across plugin/API modules (`cmd_interface`, `diagnostics_console`, `ui_schema`, `debug_bundle`, `id3_tagger`).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 6: Replace raw `isinstance(dict/list)` narrowing with typed guards at boundaries
- impact: Reduced repeat pyright reruns by preventing `Unknown` propagation from `dict[Unknown, Unknown]` and `list[Unknown]` in strict mode.
- affected workflow step or files: import cluster strict cleanup (`preview.py`, `conflicts.py`, `wizard_editor_storage.py`, `expr_eval.py`, `cli_*`, `plan.py`, `field_schema_validation.py`).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 7: Avoid custom `Mapping.get` overloads in mutable views
- impact: Prevented repeated `reportIncompatibleMethodOverride` churn by relying on inherited `MutableMapping.get` unless custom behavior is truly required.
- affected workflow step or files: strict cleanup for mapping view adapters like `plugins/import/step_catalog.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 8: Repo-wide codemod for `_is_str_object_dict` guard shape
- impact: Material reduction in lint/type iteration count by converting all key-check guards to one pyright-safe and ruff-safe expression in a single pass.
- affected workflow step or files: all strict guard helpers under `plugins/import/**`, `plugins/metadata_*`, and similar modules using `cast(dict[object, object], value).keys()` loops.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 9: Compatibility seams via typed function hooks (not `globals().get`)
- impact: Avoided repeated strict-tool churn by preserving monkeypatch/back-compat hooks without introducing `Any` from `globals()` access or pyright constant-redefinition noise.
- affected workflow step or files: compatibility entrypoints in `plugins/import/processed_registry_required.py` (`install_processed_registry_subscriber`, `_install_processed_registry_subscriber`, `_set_installed_compat`).
- safety class: instruction-only
- scope: inside current issue scope

## 2026-05-28

### Optimization 10: Pre-type argparse `choices` collections in strict `Any`-free mode
- impact: Avoided repeated strict mypy `list[Any]` leaks from `argparse.add_argument(..., choices=...)` kwargs by storing choices in explicitly typed local variables before passing them.
- affected workflow step or files: import CLI parser helpers in `plugins/import/cli.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 11: Wrap untyped third-party constructors behind typed callables
- impact: Removed strict `no-untyped-call` blockers without behavior change by casting external constructors once to `Callable[[str], object]` and keeping typed protocols at boundary reads.
- affected workflow step or files: cover metadata extraction boundary in `plugins/cover_handler/plugin.py` (`ID3`, `MP4` calls).
- safety class: instruction-only
- scope: inside current issue scope
