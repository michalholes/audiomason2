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

## 2026-06-02

### Optimization 29: Azure OpenAI-compatible endpoints require chat-completions path and bare model id
- impact: Prevents repeated 404 troubleshooting loops by using
  `.../openai/v1/chat/completions` for direct HTTP calls and sending model as bare id
  (`gpt-5.4-mini`) instead of provider/model (`human/gpt-5.4-mini`).
- affected workflow step or files: AI metadata boundary calls in
  `plugins/metadata_ai/plugin.py` and host config wiring under
  `plugins.metadata_ai.config.endpoint`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 30: Treat per-item loop default confirmations as non-manual overrides
- impact: Prevents cross-author contamination in author loops where confirming one
  author default accidentally overwrote other selected authors and degraded next-step
  suggestions.
- affected workflow step or files: PHASE 1 metadata/source projection interplay in
  `plugins/import/phase1_metadata_flow.py` and
  `plugins/import/phase1_source_intake.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 31: Drive author/title loop prompt defaults from per-book authority
- impact: Eliminates stale raw filename prompts after metadata validation by
  projecting `selected_author_label_list` and `selected_book_label_list` from
  `authority_by_book` before loop prompts render.
- affected workflow step or files: PHASE 1 source projection in
  `plugins/import/phase1_source_intake.py` with authority produced by
  `plugins/import/phase1_metadata_flow.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 30: Pyright strict inference plus unknown diagnostics is the closest Any guard
- impact: Reduces false confidence from pyright by forcing stricter collection inference and
  surfacing unknown-typed expressions at boundaries, even though pyright has no explicit Any
  diagnostic equivalent to mypy's `disallow_any_*` set.
- affected workflow step or files: `pyrightconfig.json` strict inference and `reportUnknown*`
  settings.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 32: Normalize metadata cache keys and persist successful suggestions across runs
- impact: Prevents repeated raw-title regressions under transient metadata API failures (timeouts/429)
  by reusing prior successful author/title suggestions even in new CLI processes.
- affected workflow step or files: metadata boundary cache strategy in
  `plugins/import/metadata_boundary.py` and PHASE 1 validation cache key normalization in
  `plugins/import/phase1_metadata_flow.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 33: Keep source-language book titles when suggestion looks like translation
- impact: Prevents undesired language flips (for example Czech title -> English title)
  while still accepting same-language canonicalization and typo cleanup.
- affected workflow step or files: title canonicalization in
  `plugins/import/phase1_metadata_flow.py` (`_prefer_source_title_if_translation`).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 34: Prefer unrar over 7z for RAR extract/list in mixed-tool environments
- impact: Prevents false archive failures (`Unsupported Method`) when system `7z` lacks full
  support for newer RAR methods but `unrar` is available.
- affected workflow step or files: external archive backend selection in
  `plugins/file_io/service/archives/service.py` (`_list_entries_external`,
  `_pick_external_unpack_tool`).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 35: Preserve per-entry archive source path for root-level bundle files
- impact: Prevents single-book actions from accidentally expanding an entire archive in
  PHASE 2 when the selected archive item is a root-level file.
- affected workflow step or files: archive source projection in
  `plugins/import/phase1_source_intake.py` (`_archive_pairs_for_bundle`).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 36: Stub slow validation only after orchestration state is established
- impact: Avoids changing early flow decisions and removes repeated validation delays in
  multi-step import orchestration tests by patching the validator only after session creation.
- affected workflow step or files: test helpers for import phase 1 orchestration flows,
  especially `tests/test_import_phase1_v3_orchestration_issue127.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 37: Patch validation in projection-only tests that do not assert lookup behavior
- impact: Keeps projection-focused import tests fast by bypassing hidden validation calls when
  the test only checks deterministic projection shaping.
- affected workflow step or files: `tests/test_import_phase1_v3_orchestration_issue127.py`
  projection-only cases.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 38: Stub metadata validation in end-to-end import tests that only assert state
- impact: Prevents slow or flaky acceptance tests by replacing hidden metadata lookup with a
  deterministic local stub when the test only checks launcher/plan/session state.
- affected workflow step or files: `tests/test_import_v3_acceptance_end_to_end.py` and
  `tests/test_issue214_import_plan_from_selection.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 39: Stub validation in auto-advance spec tests that only assert step flow
- impact: Prevents `pytest-timeout` on long step-flow regressions by avoiding real metadata
  validation when the test only checks hidden-step advancement and flow shape.
- affected workflow step or files: `tests/unit/test_import_wizard_spec_alignment.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 40: Persist global ID3 values only from explicit user answers
- impact: Prevents first-selected-book metadata from being applied to all books in PHASE 2
  when the ID3 step is not explicitly answered.
- affected workflow step or files: PHASE 1 authority assembly in
  `plugins/import/phase1_source_intake.py` (`phase2_inputs.id3_policy.values`).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 41: Refresh V3 plan/conflict preview after each accepted submit
- impact: Prevents false `conflicts_changed` finalize failures caused by stale preview
  fingerprints when users continue editing author/title/policy steps after first preview.
- affected workflow step or files: V3 submit path in
  `plugins/import/engine_step_submit.py` (`_needs_v3_plan_refresh` and post-submit
  `compute_plan(...)` refresh).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 42: Treat V3 auto-populated ID3 defaults as implicit, not global override
- impact: Prevents first-book title/author from being stamped onto all batch outputs when
  `id3_policy` is filled by automatic `data.set` steps.
- affected workflow step or files: PHASE 1 authority assembly in
  `plugins/import/phase1_source_intake.py` (`_explicit_id3_values` and
  `phase2_inputs.id3_policy.values`).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 43: Join scoped source paths to session source root in PHASE 2 requests
- impact: Prevents `source path missing after staging` failures for imports launched from
  nested inbox paths by serializing action source paths as root-relative.
- affected workflow step or files: PHASE 2 request assembly in
  `plugins/import/job_requests.py` (`_root_relative_source_path` and action source/delete
  path serialization).
- safety class: instruction-only
- scope: inside current issue scope

## 2026-06-07

### Optimization 44: Unblock call.invoke authority changes by publishing manifest pointer first
- impact: Reduces refactor deadlocks when introducing new import callable operations by making
  `resolve_wizard_callable(...)` pass early, before larger flow rewiring starts.
- affected workflow step or files: import plugin callable publication path in
  `plugins/import/plugin.yaml`, `plugins/import/wizard_callable_manifest.json`, and
  `plugins/import/plugin.py` method surface.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 45: Capability-gated detox avoids legacy v3 regressions
- impact: Lets new workflows drop hidden submit hooks immediately while preserving old frozen
  sessions, reducing rollout risk and rework from broad compatibility breakage.
- affected workflow step or files: v3 submit branching in
  `plugins/import/engine_step_submit.py` via explicit refresh-node detection.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 46: Convert no-op checkpoints into explicit callable refresh nodes
- impact: Replaces invisible orchestration with traceable DSL steps, reducing ambiguity during
  replay/debug and making authority drift easier to detect.
- affected workflow step or files: v3 default graph in
  `plugins/import/dsl/default_wizard_v3_source.json` (refresh checkpoints switched to
  `call.invoke` and loop confirmed writes).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 47: Make load/finalize paths consume persisted authority only
- impact: Removes hidden recompute side effects and prevents authority drift between submit and
  start-processing phases.
- affected workflow step or files: read-only session load in `plugins/import/engine.py` and
  start-processing authority usage in `plugins/import/engine_processing.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 48: Keep resume path read-only and explicit
- impact: Prevents silent state mutation during session resume, making repair behavior explicit
  and easier to validate through dedicated flows.
- affected workflow step or files: session resume boundary in
  `plugins/import/engine_session_create.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 49: Pre-seed PHASE 1 authority once before v3 initialize_state
- impact: Avoids first-prompt `missing_key` regressions while preserving detox goals by keeping
  create-time authority seeding single-pass and removing post-init recompute loops.
- affected workflow step or files: v3 create path in
  `plugins/import/engine_session_create.py`.
- safety class: instruction-only
- scope: inside current issue scope

## 2026-06-09

### Optimization 50: Parse noisy CLI JSON from the first top-level object
- impact: Prevents brittle test failures when structured output is mixed with logs by decoding
  the first top-level JSON object directly instead of scanning for the last brace line.
- affected workflow step or files: CLI capture tests such as
  `tests/test_import_cli_wizard_start_conflict_issue168.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 50: Switch planning reads to vars.phase1 first with legacy fallback
- impact: Reduces dependence on stale top-level selection mirrors while keeping compatibility
  during staged sunset of legacy state fields.
- affected workflow step or files: selection reads in
  `plugins/import/engine.py` and `plugins/import/phase1_source_intake.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 51: Scope call.invoke monkeypatches by operation_id in orchestration tests
- impact: Prevents unstable orchestration tests after explicit
  `call.invoke(import.phase1_refresh)` nodes made overbroad resolver monkeypatching drift and
  trigger false failures.
- affected workflow step or files: phase1 orchestration test patch helpers should intercept only
  `metadata.phase1_validate`, while delegating all other `operation_id` values to the original
  resolver.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 52: Freeze zero-new-runtime constraint directly in the remediation plan
- impact: Prevents authority drift where helper business logic is moved from one Python layer to
  another instead of into JSON nodes and declared primitive semantics.
- affected workflow step or files: execution constraints and SB-05/DoD criteria in
  `import_plugin_json_orchestration_plan.md`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 53: Freeze no-pytest execution policy in plan-level guardrails
- impact: Prevents churn from stale test expectations during architecture migration by separating
  implementation authority work from test-suite maintenance.
- affected workflow step or files: scope constraints and SB-06 verification criteria in
  `import_plugin_json_orchestration_plan.md`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 54: Remove contradictory gate criteria from Definition of Done
- impact: Prevents process deadlocks by keeping plan acceptance criteria consistent with explicit
  no-pytest and no-test-update scope.
- affected workflow step or files: `Definition of Done` and SB-06 verification bullets in
  `import_plugin_json_orchestration_plan.md`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 55: Add primitive granularity guardrails before helper sunset
- impact: Prevents drift where helper business logic is re-centralized into one catchall
  primitive instead of being split into atomic JSON-driven primitive contracts.
- affected workflow step or files: primitive constraints and SB-02/SB-05/DoD rules in
  `import_plugin_json_orchestration_plan.md`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 56: Convert spec-gate findings into explicit SB-05 acceptance criteria
- impact: Prevents ambiguous implementation drift by turning rule-level findings into concrete
  removal targets and hard acceptance checks for helper sunset.
- affected workflow step or files: SB-05 spec status and DoD criteria in
  `import_plugin_json_orchestration_plan.md`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 57: Seed minimal PHASE 1 state before v3 prompt entry
- impact: Avoids first-step expression failures after removing custom projection primitives by
  ensuring `vars.phase1` and loop-confirmed maps exist before `flow.invoke` passthrough refreshes.
- affected workflow step or files: session creation seed in
  `plugins/import/engine_session_create.py` and v3 submit sync in
  `plugins/import/engine_step_submit.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 58: Keep v3 legacy sync strictly mirror-only
- impact: Prevents business-orchestration drift from creeping back into submit-time Python paths by
  mirroring only persisted fields (`inputs`, selected id mirrors) instead of deriving from discovery.
- affected workflow step or files: v3 submit sync and selection validation boundaries in
  `plugins/import/engine_step_submit.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 59: Use DSL data.map/data.filter refresh nodes for per-selection state sync
- impact: Avoids hidden Python-side PHASE 1 recompute hooks while keeping selected ids, label lists,
  source paths, and cover hint arrays aligned after source/book selection edits.
- affected workflow step or files: v3 `phase1_refresh_pipeline` in
  `plugins/import/dsl/default_wizard_v3_source.json` with supporting seed keys in
  `plugins/import/engine_session_create.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 60: Remove unused source.build_catalog primitive to keep authority surface tight
- impact: Reduces accidental fallback surface and keeps PHASE 1 primitive registry aligned with
  primitives that are actually used by current import DSL flows.
- affected workflow step or files: source primitive dispatch and registry in
  `plugins/import/primitives/__init__.py` and `plugins/import/primitives/source_v1.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 61: Keep no-compat mode fail-fast on authored v3 artifact mismatches
- impact: Prevents drift from hidden compatibility rewrites by failing fast when
  authored runtime artifacts diverge from required v3 library contracts.
- affected workflow step or files: WizardDefinition load behavior discipline in
  `plugins/import/wizard_definition_model.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 62: Make PHASE 1 authority list-first and derive selection views in DSL
- impact: Reduces authority drift and fallback churn by keeping `authors[]`/`books[]`
  as canonical state and deriving prompt/selection projections via deterministic
  `data.map`/`data.filter`/`data.group_by` nodes.
- affected workflow step or files: PHASE 1 runtime seed and refresh/default pipelines in
  `plugins/import/engine_session_create.py` and
  `plugins/import/dsl/default_wizard_v3_source.json`, plus list-first consumers.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 63: Bootstrap v3 first prompt via explicit pre-entry DSL flow
- impact: Prevents empty `select_authors` options when Python-side derivation is removed by
  running deterministic PHASE 1 authority bootstrap from raw discovery before the first prompt.
- affected workflow step or files: v3 session create path in
  `plugins/import/engine_session_create.py`, bootstrap wiring and discovery-to-authority
  transform nodes in `plugins/import/dsl/default_wizard_v3_source.json`, and nested library
  invocation handling in `plugins/import/dsl/subflow_runtime.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 64: Accept typed selection payloads in source.resolve_selection
- impact: Prevents false "select one author but keep all books" behavior when prompt payloads are
  parsed as JSON number/list instead of string expression.
- affected workflow step or files: PHASE 1 selection resolution primitive in
  `plugins/import/primitives/data_v1.py` (`source.resolve_selection@1`).
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 65: Normalize metadata seed values before phase1 validation calls
- impact: Prevents early metadata validation failures (`Need author name`) by deriving
  `phase1.metadata.source_author` and `phase1.metadata.book_title` from current selected labels
  inside refresh/default pipelines before validation call nodes run.
- affected workflow step or files: PHASE 1 refresh/default pipelines and metadata validation
  chain in `plugins/import/dsl/default_wizard_v3_source.json`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 66: Hydrate plugin config before generic call.invoke callable execution
- impact: Prevents silent fallback to plugin default settings (for example disabled AI plugin)
  when a JSON `call.invoke` node executes published operations.
- affected workflow step or files: callable invocation boundary in
  `plugins/import/primitives/call_v1.py`.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 67: Stub plan computation in isolated prompt smoke tests
- impact: Keeps prompt-metadata and phase2 acceptance tests focused on rendering by bypassing
  unrelated session-authority validation during submit.
- affected workflow step or files: test-only v3 launcher smoke tests that assert prompt text and
  phase2 trace shape.
- safety class: instruction-only
- scope: inside current issue scope

### Optimization 68: Reload after prompt submits in browser smoke tests
- impact: Prevents false negatives where the backend step advances but the browser still shows the previous render until an explicit refresh.
- affected workflow step or files: v3 import UI e2e smoke tests that submit prompt steps and verify the next persisted step.
- safety class: instruction-only
- scope: inside current issue scope
