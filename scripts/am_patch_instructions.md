# AM Patch Runner 
# Patch Authoring Manual

AUTHORITATIVE – AudioMason2  
Status: active  
Version: v2.25
This manual defines what a chat must produce so that the user can run the patch successfully and close the issue.

## Absolute rules

1. The patch must be in a .patch format intended to be run by `scripts/am_patch.py -u`.
2. The patch script path MUST be under the repo patches directory (default: `/home/pi/audiomason2/patches/`). Bare filenames are resolved under `patches/`.
3. The patch MUST be served in .zip file

## Patch script requirements (must)

Constraints:
- Paths are repo-relative.
- No duplicates.
- Must be non-empty.

### 2) Deterministic behavior
- Do not use random values.
- Do not depend on time.
- Do not prompt the user for input.
- Do not require network access.

All changes must be implemented by editing files directly from Python.

### 3) Output (logging)
The runner captures stdout/stderr.
It is acceptable for the patch to print a small summary, but do not spam.
Never hide errors.

---

## What the chat must output (deliverable)

The chat must produce a patch script file that:

Canonical invocation (workspace mode):
- `python3 scripts/am_patch.py ISSUE_ID "message" [PATCH_SCRIPT]`

Notes:
- `PATCH_SCRIPT` may be `patches/<name>.zip` or just `<name>.zip` (resolved under `patches/`).
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
2. You MUST ensure patch can be applied and patched files can compile and are consistent with formatting/linting expectations. You MUST provide verifiable evidence of applyin this rule. If evidence is not provided, the patch is considered non-compliant and may be rejected without execution.
3. Avoid adding new dependencies.
4. Send out patch only as downloadable file. Only if user declare he cannot download it, send it as inline command (cat..)

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
The **last uploaded workspace snapshot** (e.g. `*.zip`) is the only authoritative state of the repository.

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
