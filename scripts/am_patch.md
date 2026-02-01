# AM Patch Runner v4 - User Manual

This manual describes how *you* use the new runner day-to-day so that runs are deterministic and issues can be safely closed.

## Concepts (minimal)

## Help

- `am_patch.py --help` shows a short, workflow-focused help.
- `am_patch.py --help-all` shows a full reference (grouped by workflow).
- `am_patch.py --test-mode` runs patch + gates in the workspace, verifies the live-repo guard (after gates), then stops (no promotion, no live gates, no commit/push, no archives) and always deletes the workspace on exit.
- `am_patch.py --show-config` prints the effective policy/config and exits.

Notes:
- Only options listed in short help have short aliases. All other options are long-only.


- **Workspace mode (default)**: runner creates/uses an issue workspace, runs patch + gates there, then promotes results to the live repo.
- **Finalize mode (-f)**: runner works directly on the live repo (no workspace). Use only when you intentionally want a direct/live operation.
- **Finalize-workspace mode (--finalize-workspace)**: runner finalizes an existing issue workspace (gates in workspace, promote to live, gates in live, commit+push). Commit message is read from workspace `meta.json`.

## What "SUCCESS" means

If the runner reports **SUCCESS** (without `-n`):
- at least one real change happened,
- no file outside `FILES` was touched,
- ruff/pytest/mypy all passed,
- promotion committed and the log reports push status (e.g. `push=OK`),
- closing the issue is justified.

If you used `-n` (allow no-op), SUCCESS does **not** imply a code change.

---

## Directory layout (expected)

- Repo root: `/home/pi/audiomason2`
- Patches root: `/home/pi/audiomason2/patches`
- Runner config (persistent): `scripts/am_patch/am_patch.toml`
- Workspaces (persistent until success): under `patches/workspaces/issue_<ID>/`
  - Finalize-workspace cleanup: on SUCCESS, the workspace is deleted if `delete_workspace_on_success=true`; use `-k` to keep it.
- Logs: under `patches/logs/` plus `patches/am_patch.log` symlink to latest log

---


## patched.zip (log + changed/touched subset) contents hygiene (size control)

`patched.zip (log + changed/touched subset)` is intended for reproducibility and review, not for mirroring the entire git repository internals or tool caches.
The runner excludes the following from the archived changed/touched subset when building `patched.zip (log + changed/touched subset)`:

- `.git/`
- `venv/`, `.venv/`
- `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`
- `__pycache__/`
- `*.pyc`

This reduces archive size without changing patch semantics or gates behavior.


## Standard workflow (workspace mode)

### 1) Create / receive a patch script
A patch script is a Python file stored under:
- `/home/pi/audiomason2/patches/`

It MUST declare a `FILES = [...]` list (repo-relative paths).

### 2) Run the patch (workspace mode)
Recommended invocation:

- `python3 scripts/am_patch.py ISSUE_ID "message" [PATCH_SCRIPT]`

Patch script location rules:
- `PATCH_SCRIPT` may be `patches/<name>.py` or just `<name>.py` (resolved under `patches/`).
- Absolute paths are accepted only if they are under `patches/`.
- Any path outside `patches/` is rejected in PREFLIGHT.

You may add:
- `-r` to run all gates even if one fails (more diagnostics)

### 3) Read the log
Open `patches/am_patch.log` (symlink to newest log).

The log contains:
- effective configuration,
- full stdout+stderr of patch and all gates,
- promotion actions,
- commit SHA on success,
- failure fingerprint on failure.

### 4) Close the issue
Only close an issue when:
- runner returned SUCCESS **without** `-n`, and
- the success log shows a commit SHA and push succeeded.

---

## Common flags

Short-help options (have short aliases):

- `-n` / `--allow-no-op` : allow no-op (otherwise no-op fails)
- `-a` / `--allow-undeclared-paths` : allow touching files outside FILES
- `-t` / `--allow-untouched-files` : allow declared-but-untouched FILES
- `-l` / `--rerun-latest` : rerun latest archived patch (auto-select from patches/successful and patches/unsuccessful)
- `-r` / `--run-all-gates` : run all gates (not only those affected by files in scope)
- `-g` / `--allow-gates-fail` : allow gates to fail (continue)
- `-c` / `--show-config` : print the effective config/policy and exit
- `-f` / `--finalize-live MESSAGE` : finalize live repo (gates + promotion by commit/push)

Long-only options (no short alias):

- `--finalize-workspace ISSUE_ID` : finalize an existing workspace (gates in workspace, promote changes to live, gates in live, then commit/push)
- `--require-push-success` : fail the run if push fails (overrides allow_push_fail)
- `--disable-promotion` : run gates, but do not commit or push (applies to patch mode and finalize modes)
- `--keep-workspace` : keep workspace on success (finalize-workspace and patch workspace mode)
- `--allow-live-changed` / `--overwrite-live` / `--overwrite-workspace` : control live-changed resolution during workspace promotion

Blessed gate outputs (no `-a` required):

- `audit/results/pytest_junit.xml` is treated as a gate-produced audit artifact.
- It does not trigger scope failures and is promoted/committed automatically when changed.

---

## When the runner FAILS (what to do)

### A) FAIL: origin/main is ahead
Meaning: remote main moved forward since your local main.

Fix:
1. Update your local main (pull/rebase) so it includes origin changes.
2. Re-run the runner.

If you intentionally want to proceed without updating:
- rerun with `-u` (not recommended except for controlled cases).

### B) FAIL: live FILES changed since workspace base

Meaning: the live repo changed in one of the promotable files after the workspace base was captured.

Fix options (choose explicitly):
1. Update the workspace base to current live base and retry:
   - rerun with `-W` / `--update-workspace`
2. Intentionally overwrite live with the workspace version:
   - rerun with `--overwrite-live`
   - or set `live_changed_resolution = "overwrite_live"`
3. Intentionally keep the live version and skip promoting the conflicting files:
   - rerun with `--overwrite-workspace`
   - or set `live_changed_resolution = "overwrite_workspace"`

Notes:
- `--allow-live-changed` is a legacy alias for `--overwrite-live`.

### C) FAIL: scope violation (touched file outside FILES)
Meaning: patch changed something outside its declared list.

Fix:
- correct the patch: add the missing file to `FILES` or stop touching it.
Then rerun.

### D) FAIL: no-op patch
Meaning: the patch produced no real change.

Fix:
- if the intent was to change code: patch is wrong; regenerate/fix it.
- if you intentionally want a dry/no-op run: rerun with `-n`.

---

## Finalize mode (-f)

Use finalize mode only when you intentionally want direct live repo operations.

Typical invocation:
- `python3 scripts/am_patch.py -r -f "message"`

Note:
- In finalize mode, positional args (ISSUE_ID / PATCH_SCRIPT) are not accepted.

Finalize mode may be used without an issue id.
It should still obey logging and gate policies, but it does not use a workspace.

---

## Operational hygiene

- Avoid running two instances at once (runner has a lock).
- Treat SUCCESS as the only safe signal to close issues.
- Keep `scripts/am_patch/am_patch.toml` under version control if you want consistent behavior across machines.


## Patch execution safety (v4.1.38+)

- Patch scripts are copied into the workspace and executed only from there.
- Patch execution is isolated via a filesystem jail (bubblewrap) by default.
- Only the workspace is writable; live repo access is denied.

### Rollback behavior

- On patch or gate failure, the workspace is rolled back to the exact state before patch execution.
- This rollback is transactional and includes tracked and untracked files.

### Ruff formatting

- `ruff format` runs before `ruff check` by default.
- Formatting is logged and included in rollback semantics.

## Post-success Audit (automatic)

When a run completes successfully **and the commit+push succeeds**, the runner automatically
executes an **AUDIT** step:

```
python3 -u audit/audit_report.py
```

What this means:
- You immediately see how the audit status changed due to the patch you just pushed.
- The audit runs on the **live repository**, not the workspace.
- In `workspace` mode and `--finalize-workspace`, the audit runs **after** workspace deletion (when enabled).
- In `--finalize-live`, there is no workspace; the audit runs after `SUCCESS`.

If the audit step fails:
- The runner reports FAILURE with stage `AUDIT`.
- The commit remains (no rollback), but the failure is visible in the log and must be addressed.

---

## patched_success.zip (SUCCESS: clean repo snapshot)

On SUCCESS, the runner creates `patched_success.zip` as `git archive HEAD` of the final live repo state.
It contains only git-tracked files and does not include logs, workspaces, caches, or patch inputs.

