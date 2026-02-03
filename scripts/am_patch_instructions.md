# AM Patch Runner 
# Patch Authoring Manual

AUTHORITATIVE – AudioMason2  
Status: active  
Version: v2.30
This manual defines what a chat must produce so that the user can run the patch successfully and close the issue.

## Absolute rules

1. The patch path MUST be under the repo patches directory (default: `/home/pi/audiomason2/patches/`). Bare filenames are resolved under `patches/`.
2. The patch MUST be served in .zip file
3. The patch MUST be a unified diff in `git apply` format (aka "unified patch"). Any Python patch scripts (.py) are non-compliant.


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

All changes must be expressed as a single unified diff patch ("git apply" format).
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

The chat must produce a patch file that:

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
4. Send out patch only as downloadable file. Only if user declare he cannot download it, send it as inline command (cat..)
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

