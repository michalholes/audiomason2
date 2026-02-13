# AM Patch Runner

# Patch Authoring Manual

AUTHORITATIVE -- AudioMason2 Status: active Version: v2.36

This manual defines what a chat must produce so that the user can run
the patch successfully and close the issue.

------------------------------------------------------------------------

## Absolute rules

1.  The patch path MUST be under the repo patches directory (default:
    `/home/pi/audiomason2/patches/`).
2.  The patch MUST be served in a `.zip` file.
3.  The patch MUST be a unified diff in `git apply` format. Python patch
    scripts are non-compliant.

------------------------------------------------------------------------

# PRE-FLIGHT GATE (HARD)

Before generating any patch, the chat MUST have:

1.  A valid ISSUE ID.
2.  An authoritative workspace snapshot (full repository or all files
    that will be modified).
3. Workspace Snapshot Format and Authority

If a single `.zip` archive is provided and it contains the full repository tree, it MUST be treated as an authoritative workspace snapshot.

No additional confirmation of authority MUST be requested from the user.

The implementing agent MUST:
- unzip the archive,
- treat its contents as the current workspace state,
- inspect the files before generating any patch.

The physical form of the snapshot (compressed archive vs. pre-unzipped directory tree) MUST NOT affect its authority.

Refusal to proceed solely on the basis that the snapshot is provided as a `.zip` archive constitutes a PRE-FLIGHT violation.

4. If any required input is missing → STOP and request missing input.



------------------------------------------------------------------------

## Anti-monolith rule set (HARD)

A chat MUST NOT create a monolith or contribute to monolith growth. The
patch MUST preserve modular boundaries and keep changes localized.

Required constraints:

1.  Locality-first: prefer the smallest change set that fixes the issue.
2.  No "god modules": do not introduce new catch-all modules.
3.  No centralization without approval.
4.  Respect ownership boundaries.
5.  New code must have a single clear responsibility.
6.  If the required change would inherently be cross-cutting, the chat
    MUST stop and request explicit permission before producing such a
    patch.

------------------------------------------------------------------------

## Per-file patch zip format (HARD)

The patch delivered to the user MUST be a `.zip` that contains one
`.patch` file per modified repository file.

Rules:

1.  For each modified repo file `path/to/file.ext`, the zip MUST contain
    exactly one patch file named:
    `patches/per_file/path__to__file.ext.patch`
2.  Each patch file MUST contain a unified diff that changes only its
    corresponding file.
3.  The zip MUST NOT contain a combined patch.
4.  The set of patch files must be non-empty.
5.  Each patch file MUST pass: `git apply --check <that_file.patch>`.

------------------------------------------------------------------------

## Patch requirements (HARD)

-   Paths are repo-relative.
-   Deterministic behavior only.
-   No randomness, no time dependence, no interactive prompts during
    runtime, no network access.
-   All changes MUST be expressed as unified diff patches, packaged per
    file.
-   `git apply --check <patch>.patch` MUST succeed.

------------------------------------------------------------------------

# INITIAL PATCH RULES (HARD)

These rules apply when generating the first patch for an issue.

## Deliverable (MANDATORY)

The chat MUST provide:

1.  A downloadable `.zip` patch under `patches/`.
2.  A canonical invocation command in a code block.
3.  The exact PATCH argument used in invocation.

Canonical invocation format (NO VARIANTS):

    python3 scripts/am_patch.py ISSUE_ID "commit message" PATCH

-   `PATCH` may be `patches/<name>.zip` or `<name>.zip`
-   Absolute paths are forbidden unless under `patches/`
-   The command MUST be provided exactly once
-   No alternative forms are allowed

If invocation command is missing or malformed, the patch is
NON-COMPLIANT.

## Validation discipline

Before sending:

1.  Patch MUST modify at least one file.
2.  Patch MUST apply cleanly (`git apply --check`).
3.  Modified files MUST compile (`python -m compileall` minimum).
4.  Patch MUST not introduce new dependencies without explicit approval.

The chat MUST NOT claim success without evidence.

The runner remains the authority.

------------------------------------------------------------------------

# REPAIR PATCH RULES (HARD)

These rules apply when user provides `patched.zip`.

## Authoritative overlay model

Authoritative file set is composed of:

1.  Last full workspace snapshot.
2.  Most recent `patched.zip`.

Per-file authority:

-   If file exists in `patched.zip`, that version is authoritative.
-   Otherwise, use version from full workspace.
-   Logs are diagnostic only.

Generating repair patch against outdated snapshot is FORBIDDEN.

Repair patches MUST follow a file-local default workflow.
The agent MUST NOT reconstruct, overwrite, or mechanically rebuild the
entire repository tree unless strictly required for correctness.

The default behavior is minimal-scope modification based on failing gate logs.

------------------------------------------------------------------------

## Repair workflow optimization (MANDATORY)

### Core principle: minimal scope

-   The agent MUST modify only the minimal set of files required to fix
    the failing gate(s).
-   The agent MUST justify any widening of scope using log evidence and
    file inspection.
-   Automatic full-tree restoration or overlay merging is prohibited.


## Ruff / Mypy failures (default-minimal workflow)

If the failing gates include `ruff` and/or `mypy`, the agent MUST:

1.  Use the provided logs to identify exact failing file paths.
2.  Restrict modifications to only the implicated files.
3.  Prefer files present in `patched.zip` when applicable.
4.  Avoid unpacking or reconstructing the full workspace unless the log
    explicitly references files outside `patched.zip`.

Fixing pure ruff/mypy failures MUST NOT trigger full repository rebuild.


## Pytest failures (triage workflow)

If the failing gates include `pytest`, the agent MUST perform triage
before escalating scope.

Minimal path (preferred):

-   If the failure can plausibly be fixed within files present in
    `patched.zip`, modifications MUST be restricted to those files.

Escalation (only when required):

-   The agent MAY inspect the full workspace snapshot ONLY if the log
    references files not included in `patched.zip`, or the failure
    depends on configuration, fixtures, test resources, packaging,
    entrypoints, or other files outside the authoritative overlay.

Even after escalation, only the minimal required files may be modified.

Mechanical replacement of the entire repository tree is prohibited.

------------------------------------------------------------------------

## FILE AUTHORITY MANIFEST (MANDATORY FOR REPAIR)

Before generating repair patch, the chat MUST output:

1.  Full list of repo files to be modified.
2.  Authority source per file:
    -   source = patched.zip
    -   or source = full workspace snapshot
3.  At least one structural anchor per file proving inspection.

Missing manifest = NON-COMPLIANT.

------------------------------------------------------------------------

## Repair validation evidence (MANDATORY)

For repair patches, the chat MUST provide evidence of:

1.  `git apply --check` success per file
2.  `python -m compileall` success (at least modified files)

If evidence is not shown, the chat MUST NOT claim patch was tested.

------------------------------------------------------------------------

## Issue closing rule

An issue may be closed only if:

-   Runner returns SUCCESS
-   Success log shows commit SHA
-   Push status line exists (e.g., `push=OK`)
-   User confirms correctness

Chats must never instruct closing based on reasoning alone.

------------------------------------------------------------------------

# Single Source of Truth (HARD)

1.  Always base patch on latest authoritative workspace.
2.  Open and inspect workspace before writing patch.
3.  No guessing or reconstruction.
4.  Workspace overrides chat history.
5.  No cross-chat memory as source of truth.
