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

## 2026-06-01

### Optimization 12: Auto-migrate stale v3 wizard artifacts that still use `effective_author`
- impact: Prevents repeated manual cleanup/debug cycles when users keep older `wizard_definition.json`; sessions self-heal to per-author loop behavior on load.
- affected workflow step or files: WizardDefinition load/bootstrap path in `plugins/import/wizard_definition_model.py` (v3 compatibility migration before validation/dispatch).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 13: Migrate stale `effective_title` to per-book title loop at load time
- impact: Avoids repeated support loops where title edits collapse into one shared prompt; old authored/runtime v3 artifacts self-heal to per-book prompts without manual reset.
- affected workflow step or files: v3 compatibility migration and default flow seed in `plugins/import/wizard_definition_model.py` and `plugins/import/dsl/default_wizard_v3_source.json`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 14: Keep per-item manual overrides authoritative despite metadata suggestions
- impact: Prevents repeated user-facing churn where explicitly entered author/title values appear uneditable because canonical suggestions silently overwrite them during per-item loops.
- affected workflow step or files: per-item override branch in `plugins/import/phase1_metadata_flow.py` (`author_overrides_by_book` / `title_overrides_by_book`).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 15: Reuse discovery file sizes to drop zero-byte audio books before selection
- impact: Prevents wasted import runs and failed processing jobs by filtering invalid (0B audio-only) books at PHASE 1 selection time without expensive probing.
- affected workflow step or files: discovery payload (`plugins/import/discovery.py`) and source projection filtering (`plugins/import/phase1_source_intake.py`).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 16: Re-run automatic v3 steps after PHASE 1 authority refresh
- impact: Avoids stale prompt interactions where a just-submitted selection changes `autofill_if` truth for the next prompt (for example, select source -> single remaining book), but the wizard still asks due to pre-refresh state.
- affected workflow step or files: v3 submit path in `plugins/import/engine_step_submit.py` (refresh `vars.phase1` before and after a follow-up `run_automatic_steps(...)` pass).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 17: Derive archive author/book pairs from internal audio paths
- impact: Prevents archive filename labels (for example `sp.rar`) from leaking into PHASE 1 metadata suggestions by projecting bundle selections from internal directory structure first.
- affected workflow step or files: archive source projection in `plugins/import/phase1_source_intake.py` (`_archive_pairs_for_bundle`, wrapper-folder stripping by archive stem, and non-introspected bundle fallback labels).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 18: Use root-level audio filename stem as archive fallback label
- impact: Removes ambiguous generic source labels (for example `sp`) when archives contain audio files directly at root; keeps selection labels tied to actual content.
- affected workflow step or files: archive fallback labeling in `plugins/import/phase1_source_intake.py` (`_audio_entry_stem` used by `_archive_pair_labels`).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 19: Keep CLI selection aliases and runtime parser in lockstep
- impact: Prevents user-facing validation failures where prompts advertise shorthand input (`a` for all) but runtime rejects it as out-of-range.
- affected workflow step or files: selection expression parser and submit validation in `plugins/import/engine_util.py` and `plugins/import/engine_step_submit.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 20: Reuse persisted PHASE 1 authority when computing plan
- impact: Prevents `invalid selected_book_ids` errors after valid selections when planner fallback lacks archive introspection context (for example bundle-derived books).
- affected workflow step or files: planner invocation in `plugins/import/engine.py` (pass `state.vars.phase1` as `session_authority` to `plugins/import/plan.py`).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 21: Infer one dominant author for single-level archive catalogs
- impact: Reduces repetitive author confirmations by grouping archive books under one inferred
  author when entry names show a consistent author hint.
- affected workflow step or files: archive projection helpers in
  `plugins/import/phase1_source_intake.py` (`_bundle_author_hint`, `_author_hint_from_label`,
  and single-level `_archive_pair_labels` handling).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 22: Render cover autodetection as per-book multiline summary
- impact: Prevents unreadable flat hint strings during multi-book imports by presenting
  deterministic one-line entries per selected source/book.
- affected workflow step or files: cover summary formatter in
  `plugins/import/phase1_cover_flow.py` (`_build_cover_summary`).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 23: Add explicit per-book cover decision loop to PHASE 1
- impact: Enables independent cover decisions per selected book (`file`, `embedded`, `skip`,
  `url`) instead of forcing one global cover mode for the entire batch.
- affected workflow step or files: cover projection and loop sync in
  `plugins/import/phase1_cover_flow.py` and `plugins/import/engine_step_submit.py`, plus
  runtime WizardDefinition migration in `plugins/import/wizard_definition_model.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 24: Avoid unsupported nested ExprRef indexing in v3 prompt nodes
- impact: Prevents runtime `INVARIANT_VIOLATION` (`unexpected_token`) when per-book cover mode
  is selected, by keeping prompt input expressions within supported interpreter grammar.
- affected workflow step or files: v3 cover-loop node normalization in
  `plugins/import/wizard_definition_model.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 25: Do not require URL answer on non-URL cover modes
- impact: Prevents `INVARIANT_VIOLATION` (`missing_key`) after selecting `skip`, `file`, or
  `embedded` in per-book cover loop by removing unconditional reads of URL-only answers.
- affected workflow step or files: `store_cover_item` normalization in
  `plugins/import/wizard_definition_model.py` and URL fallback handling in
  `plugins/import/engine_step_submit.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 26: Primitive-aware replay payload mapping for deterministic wizard debugging
- impact: Prevents replay-time `VALIDATION_ERROR` churn by enforcing exact payload keys per
  primitive (`selection` for `ui.prompt_select`, `value` for `ui.prompt_text`, `confirmed` for
  `ui.prompt_confirm`) and using `start_processing(confirm=true)` as the authoritative finalize
  path.
- affected workflow step or files: import replay/debug workflow and guidance in `AGENTS.md`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 27: Replace strict ranking lambdas with typed key helpers
- impact: Reduces strict `Any` churn in sort-key expressions by keeping key callables explicitly
  typed and reusable.
- affected workflow step or files: archive author ranking in
  `plugins/import/phase1_source_intake.py` (`_bundle_author_hint`).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 28: Keep import test fixtures aligned with audio-only discovery filters
- impact: Avoids broad false-negative test clusters when PHASE 1 intake accepts only audio
  suffixes; fixture-only updates restore parity without runtime code changes.
- affected workflow step or files: import selection and parity tests using fixture trees in
  `tests/test_import_runtime_v3_parity.py`,
  `tests/test_import_ui_step_projection_route.py`,
  `tests/test_import_web_runtime_v3_prompt_metadata.py`,
  `tests/test_issue214_import_plan_from_selection.py`,
  `tests/unit/test_import_finalize_success_artifacts_issue130.py`,
  `tests/unit/test_import_spec_regressions_issue217.py`, and
  `tests/unit/test_import_wizard_spec_alignment.py`.
- safety class: instruction-only
- scope: inside current issue scope
