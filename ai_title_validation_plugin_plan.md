# AI Title Validation Plugin - Implementation Plan

## Goal

Add a new plugin that asks an AI service whether the entered author name and book title
in the import flow are correct, and if not, returns a corrected book title suggestion.

## Scope and Constraints

- Do not implement code before specification anchoring.
- Keep existing OpenLibrary-first behavior intact.
- Treat AI validation as an additive correction layer.
- Keep deterministic behavior and fail-safe fallback semantics.

## Step 1 - Specification First

1. Update `governance/specification.jsonl` in a separate spec commit.
2. Add explicit rule(s) that allow AI-assisted title validation in Import PHASE 1.
3. Preserve existing parity requirements for OpenLibrary primary validation and Google
   Books fallback.

## Step 2 - New Plugin

Create a new plugin:

- `plugins/metadata_ai/plugin.py`
- `plugins/metadata_ai/plugin.yaml`
- `plugins/metadata_ai/wizard_callable_manifest.json`

Plugin callable contract:

- operation id: `metadata.ai_title_validate`
- execution mode: `job`
- input: `{author, title}`
- output shape compatible with existing Phase 1 metadata validation payload semantics
  (`author`, `book`, `provider`).

## Step 3 - AI Boundary Behavior

1. Use OpenAI-compatible HTTP API settings from plugin config.
2. Enforce strict JSON response contract from model output.
3. Use deterministic request settings (`temperature=0`).
4. Add timeout and maximum response size safeguards.
5. Add in-memory cache keyed by `(author, title)`.
6. On any provider failure, return neutral no-op payload instead of raising a hard error.

## Step 4 - Import Integration

Integrate in import metadata boundary:

- file: `plugins/import/metadata_boundary.py`
- keep existing `metadata.phase1_validate` resolution and behavior
- add optional AI callable invocation and merge strategy

Merge strategy:

1. Keep OpenLibrary/Google pipeline as baseline authority.
2. Allow AI to suggest corrected title when baseline result is uncertain or non-exact.
3. Do not break existing payload keys expected by PHASE 1 flow projection.

## Step 5 - Phase 1 Projection Consistency

Ensure the merged validation output is applied consistently in:

- explicit validation answer branches (`metadata_validate_initial`,
  `metadata_validate_after_author`, `metadata_validate_after_title`)
- per-book override branch after author/title edits

Target file:

- `plugins/import/phase1_metadata_flow.py`

## Step 6 - Prompt Hint Updates

Optionally adjust user-facing hint text to indicate when a canonical suggestion comes
from AI-assisted validation, without changing renderer payload contracts.

## Step 7 - Documentation Fragment

When implementation changes are made in `plugins/` and/or `docs/`, add a new file in:

- `docs/change_fragments/`

Follow canonical fragment naming and content format required by repository governance.

## Step 8 - Tests

Add tests for:

1. New plugin success path with deterministic AI JSON output.
2. Provider failures: timeout, invalid JSON, empty response.
3. Import flow integration where AI suggests corrected title.
4. Regression: unchanged behavior when AI plugin is unavailable or disabled.

## Step 9 - Validation and Delivery

1. Run quality gates (`ruff`, `mypy`, `pytest`).
2. Run Amp patch runner as final gate.
3. Deliver in governance-compliant commit sequence:
   - spec change commit first
   - implementation commit(s) after spec
