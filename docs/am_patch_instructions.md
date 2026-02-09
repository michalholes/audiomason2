# AM Patch Runner 
# Patch Authoring Manual

AUTHORITATIVE – AudioMason2  
Status: active  
Version: v2.32
This manual defines what a chat must produce so that the user can run the patch successfully and close the issue.

## Absolute rules

1. The patch path MUST be under the repo patches directory (default: `/home/pi/audiomason2/patches/`). Bare filenames are resolved under `patches/`.
2. The patch MUST be served in .zip file
3. The patch MUST be a unified diff in `git apply` format (aka "unified patch"). Any Python patch scripts (.py) are non-compliant.


## Anti-monolith rule set (HARD)

A chat MUST NOT create a monolith or contribute to monolith growth. The patch MUST preserve modular boundaries and keep changes localized.

Required constraints:

1. Locality-first: prefer the smallest change set that fixes the issue.
2. No “god modules”: do not introduce new catch-all modules (e.g., `utils.py`, `common.py`, `helpers.py`, `misc.py`) that aggregate unrelated responsibilities.
3. No centralization without approval: do not move many unrelated functions/classes into a single new location “for reuse” unless the user explicitly requested that refactor.
4. Respect ownership boundaries: avoid cross-cutting edits across many packages/subsystems when a narrow fix is possible.
5. New code must have a single clear responsibility and belong to the closest existing module where that responsibility naturally fits.
6. If the required change would inherently be cross-cutting (touching many subsystems), the chat MUST stop and request explicit permission with a concrete scoped plan before producing such a patch.

## Per-file patch zip format (HARD)

The patch delivered to the user MUST be a `.zip` that contains **one `.patch` file per modified repository file**.

Rationale: if patching one file fails, unaffected files must still be applicable independently.

Rules:

1. For each modified repo file `path/to/file.ext`, the zip MUST contain exactly one patch file named:
   - `patches/per_file/path__to__file.ext.patch`
   - where `/` is replaced with `__`.
2. Each patch file MUST contain a unified diff that changes **only** its corresponding file.
   - No multi-file diffs.
   - No `diff --git` entries for other files.
3. The zip MUST NOT contain a “combined” patch.
4. The set of patch files must be non-empty.
5. Each patch file MUST pass: `git apply --check <that_file.patch>`.
6. Optional but recommended: include a short ASCII-only `patches/per_file/MANIFEST.txt` listing patch filenames in application order (one per line). If present, the order MUST be deterministic (lexicographic by patch filename).

Notes:
- The runner invocation still points to the single `.zip` file; the runner will apply per-file patches from inside it.
- If the runner does not yet support this, the correct action is to update the runner first (separately), not to violate this manual.

## Patch requirements (must)

Constraints:
- Paths are repo-relative.
- No duplicates.
- Must be non-empty.

### 2) Deterministic behavior
- Do not use random values.
- Do not depend on time.
- Do not prompt the user for input.
- Do not require network access.

All changes must be expressed as unified diff patches ("git apply" format), packaged **per file** (see “Per-file patch zip format”).
Forbidden:
- generating any `.py` patch script
- embedding runnable Python code as the patch mechanism

Validation expectation (MUST):
- `git apply --check <patch>.patch` must succeed


### 3) Output (logging)
The runner captures stdout/stderr.
It is acceptable for the patch to print a small summary, but do not spam.
Never hide errors.

---

## What the chat must output (deliverable)

The chat must produce a patch zip that:

Canonical invocation (workspace mode):
- `python3 scripts/am_patch.py ISSUE_ID "message" [PATCH]`
The chat must under the download link publish in code box command for invocation.
 
Notes:
- `PATCH` may be `patches/<name>.zip` or just `<name>.zip` (resolved under `patches/`).
- Absolute paths are rejected unless they are under `patches/`.

- resides under `/home/pi/audiomason2/patches/` (user will place it there),
- is ASCII-only by default (unless the runner policy explicitly disables ASCII enforcement),
- applies the intended change,
- and leaves the repository in a state where:
  - ruff passes,
  - pytest passes,
  - mypy passes.

The chat must not claim success without evidence.
The runner is the authority.

---

## Patch authoring checklist (before sending)

1. You MUST ensure the patch changes at least one file.
2. You MUST ensure patch can be applied and patched files can compile and are consistent with formatting/linting expectations. You MUST provide verifiable evidence of applying this rule. If evidence is not provided, the patch is considered non-compliant and may be rejected without execution.
3. Avoid adding new dependencies.
4. Send out patch only as downloadable file. Only if user declare he cannot download it, send it as inline command (cat..). In that case, runner can accept raw .patch filea, so provide in code box command with path to raw patch.
5. The patch content MUST look like a unified diff (e.g. contains `diff --git` and `---`/`+++`/`@@` hunks). If the output contains Python code intended to perform edits, it is non-compliant.

---

## “Issue can be closed” rule

An issue can be closed only if:
- the runner returns SUCCESS, and
- the success log shows commit SHA and a push status line (e.g. `push=OK`)
- commands to smoke tests was provided
- user said "everything is ok" or similar

Chats must never instruct the user to close the issue based on chat reasoning alone.

---

## Common failure causes (and what to fix)

- Gates fail: fix code/test/type issues.

## Authoritative workspace rule (HARD)

**Single source of truth:**  
Mandatory rules for chats producing patches:

1. **Always base the patch on the latest workspace.**  
   The chat MUST assume that any earlier description, memory, or previous patch attempt is obsolete once a new workspace is uploaded.

2. **Open the workspace before writing a patch.**  
   The chat MUST inspect the actual files from the latest workspace and derive changes from their real contents.

3. **No guessing, no reconstruction.**  
   If a required snippet is not found in the workspace, the chat MUST stop and request clarification or a newer workspace instead of inventing changes.

4. **Workspace beats chat history.**  
   In case of conflict, the workspace snapshot always wins over:
   - earlier chat messages,
   - previous patches,
   - assumed repository state.

Violations of this rule typically result in:
- incorrect patches,
- or silent logical corruption.

This rule is absolute and overrides all informal reasoning.


## File authority, inspection & repair rules (HARD)

1. The chat MUST open and inspect **every uploaded file or archive** (`*.log`, `*.zip`, patches, sources) before any conclusion or patch.

2. The initial workspace upload defines the authoritative version of all files it contains.

3. Authority is applied **per file**, never globally:  
   any file present in a patched upload replaces its older versions; files not present remain authoritative from the most recent earlier upload.

4. Upload order determines authority **only per file**, never for the entire workspace.

5. Logs are authoritative **only for failure diagnosis** and never change file authority.

6. If a log or patch references a file whose authoritative version is unavailable, the chat MUST stop and request that file.

7. The chat MUST NOT ask questions if sufficient authoritative inputs are present.

8. When files are uploaded, the chat MUST NOT rely on prior conversation context, assumptions, or summaries; **only uploaded files are authoritative**.

9. The chat MUST NOT use **inter-chat or cross-conversation memory** as a source of truth under any circumstances.

