# AM Patch Runner

# Patch Authoring Manual

AUTHORITATIVE - AudioMason2 Status: active Version: v2.33

This manual defines what a chat must produce so that the user can run
the patch successfully and close the issue.

## Absolute rules

1.  The patch path MUST be under the repo patches directory (default:
    `/home/pi/audiomason2/patches/`). Bare filenames are resolved under
    `patches/`.
2.  The patch MUST be served in .zip file.
3.  The patch MUST be a unified diff in `git apply` format (aka "unified
    patch"). Any Python patch scripts (.py) are non-compliant.

## Anti-monolith rule set (HARD)

A chat MUST NOT create a monolith or contribute to monolith growth. The
patch MUST preserve modular boundaries and keep changes localized.

Required constraints:

1.  Locality-first: prefer the smallest change set that fixes the issue.
2.  No "god modules": do not introduce new catch-all modules (e.g.,
    `utils.py`, `common.py`, `helpers.py`, `misc.py`) that aggregate
    unrelated responsibilities.
3.  No centralization without approval.
4.  Respect ownership boundaries.
5.  New code must have a single clear responsibility.
6.  If the required change would inherently be cross-cutting, the chat
    MUST stop and request explicit permission before producing such a
    patch.

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

## Patch requirements (must)

-   Paths are repo-relative.
-   Deterministic behavior only.
-   No randomness, no time dependence, no prompts, no network access.
-   All changes must be expressed as unified diff patches, packaged per
    file.

Validation expectation (MUST): `git apply --check <patch>.patch` must
succeed.

## Authoritative workspace rule (HARD)

Single source of truth:

1.  Always base the patch on the latest authoritative workspace.
2.  Open and inspect the workspace before writing a patch.
3.  No guessing or reconstruction.
4.  Workspace snapshot overrides chat history.

## File authority, inspection & repair rules (HARD)

1.  The chat MUST open and inspect every uploaded file or archive before
    any conclusion or patch.
2.  Authority is applied per file, never globally.
3.  Files present in a patched upload replace older versions of the same
    file.
4.  Logs are authoritative only for diagnostics.

  -----------------------------------------------
  REPAIR WORKFLOW: AUTHORITATIVE OVERLAY (HARD)
  -----------------------------------------------

When a previous patch failed and the user provides `patched.zip`, the
authoritative file set is composed as follows:

1.  Last full workspace snapshot.
2.  Most recent `patched.zip`.

Per-file authority:

-   If a file exists in `patched.zip`, that version is authoritative.
-   If not, use the version from the full workspace snapshot.
-   Logs are diagnostic only and never override file authority.

It is forbidden to generate a repair patch against only the original
full snapshot if newer file versions exist in `patched.zip`.

  --------------------------------------------
  FILE AUTHORITY MANIFEST (HARD REQUIREMENT)
  --------------------------------------------

Before generating any repair patch, the chat MUST output a FILE
AUTHORITY MANIFEST that includes:

1.  Full list of repository files to be modified.
2.  Explicit authority source for each file:
    -   source = patched.zip
    -   or
    -   source = full workspace snapshot
3.  At least one structural anchor per file (function/class/context)
    proving inspection.

If this manifest is missing or incomplete, the patch is NON-COMPLIANT.

  -----------------------------------
  REPAIR VALIDATION EVIDENCE (HARD)
  -----------------------------------

For repair patches, the chat MUST provide verifiable evidence of:

1.  Successful `git apply --check` for each per-file patch.
2.  Successful compilation via `python -m compileall` (at least for
    modified files).

If evidence is not shown, the chat MUST NOT claim the patch was tested.

The runner remains the final authority.
