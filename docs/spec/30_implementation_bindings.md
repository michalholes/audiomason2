# AudioMason2 - Implementation Bindings Specification (Authoritative)

Specification Version: 1.1.23

This document contains the LAYOUT layer of the AudioMason2
specification. It defines normative file locations, on-disk artifacts,
and other implementation bindings.

------------------------------------------------------------------------

## 10.7 Storage Model (File IO Root) and Artifacts

All Import Wizard data MUST be stored under the file_io root:

`<wizards_root>`{=html}/import/

Required subpaths:

-   catalog/catalog.json
-   flow/current.json
-   config/flow_config.json
-   sessions/`<session_id>`{=html}/effective_model.json
-   sessions/`<session_id>`{=html}/effective_config.json
-   sessions/`<session_id>`{=html}/discovery.json
-   sessions/`<session_id>`{=html}/state.json
-   sessions/`<session_id>`{=html}/decisions.jsonl
-   sessions/`<session_id>`{=html}/plan.json
-   sessions/`<session_id>`{=html}/job_requests.json Notes:
-   sessions/`<session_id>`{=html}/effective_model.json MUST contain the
    frozen effective workflow snapshot derived from WizardDefinition and
    FlowConfig. UI layers MUST NOT interpret global WizardDefinition
    directly for an active session. For select_authors and select_books,
    effective_model.json MUST include items\[\] for the
    multi_select_indexed selection fields.

Engine-derived artifacts (engine-owned; may be created
deterministically):

-   sessions/`<session_id>`{=html}/action_jobs.json
    -   Meaning: canonical job requests for action steps with
        execution="job" within PHASE 1.
    -   Contract: each entry MUST be canonical JSON and MUST be
        compatible with the job subsystem.
    -   action_jobs.json MUST NOT be used for PHASE 2 processing jobs
        (see 10.11).
-   previews/`<preview_id>`{=html}.json
    -   Meaning: isolated preview_action result artifact (10.23 / 10.23
        Preview Execution).
    -   MUST NOT modify any session snapshot.
-   sessions/`<session_id>`{=html}/discovery_fingerprint.txt
    -   Content: `<hex>`{=html} + newline
    -   Meaning: SHA-256 fingerprint of canonical JSON discovery set
        (10.8).
-   sessions/`<session_id>`{=html}/effective_config_fingerprint.txt
    -   Content: `<hex>`{=html} + newline
    -   Meaning: SHA-256 fingerprint of canonical effective_config
        snapshot.
-   sessions/`<session_id>`{=html}/conflicts.json
    -   Content: canonical JSON list of conflict items.
    -   Meaning: persisted conflict snapshot used by deterministic
        conflict re-check.
-   sessions/`<session_id>`{=html}/idempotency.json
    -   Content: canonical JSON object tracking idempotency_key mappings
        for job creation.
    -   Meaning: prevents duplicate job creation for repeated
        start_processing calls.

If present, these artifacts MUST be written atomically (temp + rename).

Creation timing: - plan.json MUST be created/updated by compute_plan
(10.11). - job_requests.json MUST be created only when start_processing
is accepted and a job is requested (10.11.4).

plan.json baseline schema additions (normative): - selected_books: list
of selected book units (book_id, label, source_relative_path,
proposed_target_relative_path) - summary.selected_books: count of
selected books - summary.discovered_items: count of discovery items

Resume-after-restart is mandatory where specified by runtime mode policy
(10.9). All writes MUST be atomic (write temp, then rename).

### 10.7.1 Model Bootstrap When Missing

If catalog/catalog.json, flow/current.json, or config/flow_config.json
do not exist under the file_io root "wizards", the import plugin MUST
deterministically bootstrap them from built-in defaults.

Bootstrap rules: - Creation MUST be atomic (write temp, then rename). -
Existing files MUST NOT be overwritten. - Bootstrapped models and config
MUST pass full model validation. - Bootstrap MUST occur before first
model load. - Absence of models MUST NOT cause a hard failure if
bootstrap succeeds.

## 10.8 Deterministic Discovery (PHASE 0)

Discovery MUST produce a canonical discovery input set.

Each item MUST contain: - item_id - root - relative_path - kind
(file\|dir\|bundle)

Bundle classification rules: - kind MUST be "bundle" for files whose
relative_path ends with one of: .zip, .tar, .tgz, .tar.gz, .tar.bz2,
.rar - Extension matching MUST be case-insensitive.

Canonical ordering: 1) root (ASCII lexicographic) 2) relative_path
(ASCII lexicographic) 3) kind

item_id MUST equal: root:`<root>`{=html}\|path:`<relative_path>`{=html}

relative_path MUST: - use "/" separators - contain no ".", "..", empty
segments, or leading slash

discovery_fingerprint MUST equal: SHA-256(canonical JSON discovery set)

Persisted per session in: state.derived.discovery_fingerprint

## 10.9 Session Snapshot Isolation and Persistence Model

At session start, the engine MUST create an immutable snapshot: -
effective_config.json (FlowConfig snapshot for the session) -
effective_model.json (FlowModel snapshot for the session)

Active sessions MUST use their snapshot for their entire lifetime.
Configuration changes MUST affect only new sessions.

Persistence requirements: - Web mode: full session persistence on disk
is mandatory (crash recovery required). - CLI mode: full session
persistence may be in-memory, but snapshot semantics still apply.

## 10.10 Determinism Closure (Session Identity Tuple)

A session is deterministically defined by: - model_fingerprint (SHA-256
over canonical effective_model.json) - model_fingerprint MUST be
computed over the final persisted effective_model.json after all
enrichment steps (for example, selection items injection). -
discovery_fingerprint - effective_config_fingerprint (SHA-256 over
canonical effective_config.json) - validated user inputs (canonical
forms)

Finalize MUST produce byte-identical canonical job_requests.json for
identical tuples.

## 10.10A PHASE 1 Action Job Request Schema (Normative)

For action steps with execution == "job", the interpreter MUST create
entries inside:

sessions/`<session_id>`{=html}/action_jobs.json

Each entry MUST conform EXACTLY to the canonical job request schema
defined in Section 10.11 (Job Request Contract - PHASE 2).

Normative rules:

-   The JSON structure MUST match the same schema used by PHASE 2
    processing jobs.
-   No additional keys MAY be introduced.
-   Required keys MUST NOT be omitted.
-   job_id generation MUST follow the same deterministic rules as PHASE
    2 jobs.
-   action_jobs.json is limited strictly to PHASE 1 action steps.
-   PHASE 2 processing jobs remain governed exclusively by Section
    10.11.

Any deviation from the canonical Job Request schema SHALL be treated as
CONTRACT_VIOLATION.

------------------------------------------------------------------------

## 10.11 Job Request Contract (PHASE 2)

job_requests.json MUST contain: - config_fingerprint (SHA-256 over
canonical effective_config.json) - job_type - job_version - session_id -
actions\[\] - diagnostics_context

All file references MUST use (root, relative_path). Absolute paths are
forbidden.

actions\[\] contract (normative): - actions\[\] MUST be derived from
sessions/`<session_id>`{=html}/plan.json. - actions\[\] MUST contain one
entry per planned unit (selected_books\[\]). - If selected_books\[\] is
empty and plan.source.relative_path is non-empty, actions\[\] MUST
contain exactly one implicit unit.

start_processing response contract (normative): - start_processing MUST
return batch_size equal to the number of planned units represented in
job_requests.json actions\[\].

### 10.11.1 Canonical Serialization (Mandatory)

All job request serialization MUST be canonical: - JSON keys sorted -
books (or per-book entries) sorted by canonical key (book_id or stable
(root,relative_path) key) - paths normalized (no duplicate separators;
no traversal segments) - no volatile fields (timestamps, random IDs) in
canonical output

A shared canonical_serialize utility MUST exist and MUST be used by: -
golden tests - parity comparisons (if any) - job_requests.json
persistence

### 10.11.2 Idempotency Key (Mandatory)

Each created job MUST have a deterministic idempotency_key.

Recommended formula: hash(book_id + canonical_config_snapshot)

Rules: - Duplicate job creation with the same idempotency_key MUST be
prevented. - Duplicate start_processing calls MUST not create duplicate
jobs. - Registry updates MUST remain safe under retries.

### 10.11.3 Registry Updates (SUCCESS-only)

The processed registry MUST be updated only when the corresponding job
finishes with SUCCESS. FAILED jobs MUST NOT update the registry.

### 10.11.4 Conflict Re-check Before Job Creation (Mandatory)

Before creating jobs: - If conflict_mode == "ask": re-run conflict scan
and abort if unresolved conflicts remain. - If conflict_mode != "ask":
ensure no new filesystem conflicts appeared since preview.

Conflict scan inputs (normative): - conflict scan MUST use planned
target outputs from sessions/`<session_id>`{=html}/plan.json
(selected_books\[\].proposed_target_relative_path) rather than raw
discovery. - conflict items MUST be deterministically sorted by: 1)
target_relative_path (ASCII lexicographic) 2) source_book_id (ASCII
lexicographic) - minimal conflict item schema: - target_relative_path -
reason (exists\|unknown) - source_book_id

If conflicts appear, the engine MUST block processing deterministically
and return a structured error.

### 10.7.2 Editor Storage Layout (Deterministic)

Active: - import/config/flow_config.json -
import/definitions/wizard_definition.json

Draft: - import/config/flow_config.draft.json -
import/definitions/wizard_definition.draft.json

History: -
import/editor_history/`<kind>`{=html}/`<fingerprint>`{=html}.json -
import/editor_history/`<kind>`{=html}/index.json

Index.json MUST: - contain a unique list of fingerprints - be ordered
most-recent-first - be bounded to 5 entries

Fingerprint definition: - SHA-256 over canonical JSON bytes - canonical
JSON bytes use: ensure_ascii=True, sort_keys=True, separators=(",",
":") - fingerprint is computed WITHOUT the trailing newline used when
writing files

Persisted artifacts MUST NOT include timestamps or editor metadata
fields.
