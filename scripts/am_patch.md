# AM Patch Runner v4 - User Manual

This manual describes how *you* use the new runner day-to-day so that runs are deterministic and issues can be safely closed.

## Concepts (minimal)


### Gates and COMPILE
- After the patch is applied, the runner executes gates.
- Optional diagnostics: if patch apply fails, you can still run workspace gates for diagnostics:
  - --gates-on-partial-apply (or cfg key gates_on_partial_apply=true)
  - --gates-on-zero-apply (or cfg key gates_on_zero_apply=true)
  - The run remains FAIL with PATCH_APPLY as the primary reason.
- Gate: COMPILE runs `python -m compileall -q` in the workspace repo root to catch syntax errors early.
- Default: enabled.
- Config keys:
  - `compile_check = true|false`
  - `compile_targets = ["...", ...]` (default: `["."]`)
  - `compile_exclude = ["...", ...]` (default: `[]`)
- CLI:
  - `--no-compile-check` disables it for the run.
  - `--override compile_targets=...` and `--override compile_exclude=...` use the same list format as `ruff_targets`.

## Help

- `am_patch.py --help` shows a short, workflow-focused help.
- `am_patch.py --help-all` shows a full reference (grouped by workflow).
- `am_patch.py --test-mode` runs patch + gates in the workspace, verifies the live-repo guard (after gates), then stops (no promotion, no live gates, no commit/push, no archives) and always deletes the workspace on exit.
- In --test-mode, if patch_dir is not explicitly set, the runner isolates its work paths under patches/_test_mode/issue_<ID>_pid_<PID>/ and deletes it on exit.
- `am_patch.py --show-config` prints the effective policy/config and exits.

Notes:
- Only options listed in short help have short aliases. All other options are long-only.


## Verbosity and status output



The runner supports 5 verbosity modes for console output (and the same level names for the file log filter).

Levels are inherited: each higher mode includes everything from the lower mode.

- quiet: START + FINAL SUMMARY only (no status bar)
- normal: quiet + INFO (no CORE; no DEBUG; no status bar)
- warning: normal + WARNING + ERROR (no CORE; no DEBUG; no status bar)
- verbose: warning + CORE (INFO/WARNING/ERROR) + status bar
- debug: verbose + DETAIL + DEBUG (everything) + status bar

The runner supports an independent file log filter:

- `--log-level {quiet,normal,warning,verbose,debug}`

Both `--verbosity` and `--log-level` use the same level names and meanings, but may be set to different values.

Inheritance rule (contract):

- Verbosity modes are cumulative.
  Each higher mode MUST include all guaranteed outputs of the lower mode.

Final summary (at the end of each run):

- FILES block (only when PUSH: OK), strictly in the following format:


    FILES:

    A path1
    M path2
    D path3
  - `COMMIT: <sha>` (or `(none)` if commit/push dont runs)
  - `PUSH: OK|FAIL|UNKNOWN` (if commit/push is running)
  - `LOG: <path>`
- FAIL:
  - `RESULT: FAIL`
  - `STAGE: <stage-id>`
  - `REASON: <one path>`
  - `LOG: <path>`

- **Workspace mode (default)**: runner creates/uses an issue workspace, runs patch + gates there, then promotes results to the live repo.
- **Finalize mode (-f)**: runner works directly on the live repo (no workspace). Use only when you intentionally want a direct/live operation.
- **Finalize-workspace mode (--finalize-workspace)**: runner finalizes an existing issue workspace (gates in workspace, promote to live, gates in live, commit+push). Commit message is read from workspace `meta.json`.

## What "SUCCESS" means

If the runner reports **SUCCESS** (without `-o`):
- at least one real change happened,
- no file outside `FILES` was touched,
- ruff/pytest/mypy all passed,
- promotion committed and the log reports push status (e.g. `push=OK`),
- closing the issue is justified.

If you used `-o` (allow no-op), SUCCESS does **not** imply a code change.

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

-
Note on `-w` / `--finalize-workspace`:
- On failure (e.g. a gate fails), `patched.zip` includes the log plus the workspace changed/touched subset,
  including the files that were planned for promotion.


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
- runner returned SUCCESS **without** `-o`, and
- the success log shows a commit SHA and push succeeded.

---

## Common flags

Short-help options (have short aliases):

- `-o` / `--allow-no-op` : allow no-op (otherwise no-op fails)
- `-a` / `--allow-undeclared-paths` : allow touching files outside FILES
- `-t` / `--allow-untouched-files` : allow declared-but-untouched FILES
- `-l` / `--rerun-latest` : rerun latest archived patch (auto-select from patches/successful and patches/unsuccessful)
- `-u` / `--unified-patch` : force unified patch mode.
  - Auto-detect without `-u`:
    - input `*.patch` => unified mode
    - input `*.py` => patch script mode
    - input `*.zip` => scan zip recursively; if any `*.patch` entries exist, unified mode is used and **all** `*.patch` entries are applied (deterministic lexicographic order by zip path). If the zip also contains `*.py`, those are ignored when at least one `*.patch` exists.
- `-r` / `--run-all-gates` : run all gates (not only those affected by files in scope)
- `-g` / `--allow-gates-fail` : allow gates to fail (continue)
- `-c` / `--show-config` : print the effective config/policy and exit
- `-f` / `--finalize-live MESSAGE` : finalize live repo (gates + promotion by commit/push)

Logging / output:

- `--log-level {quiet,normal,warning,verbose,debug}` : filter what is written to the log file (independent from `--verbosity`).

Long-only options (no short alias):

- `-w` / `--finalize-workspace ISSUE_ID` : finalize an existing workspace (gates in workspace, promote changes to live, gates in live, then commit/push)
- `--require-push-success` : fail the run if push fails (overrides allow_push_fail)
- `--no-compile-check` : disable the COMPILE gate (`python -m compileall`) for this run.
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
- if you intentionally want a dry/no-op run: rerun with `-o`.

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

## Success archive (SUCCESS: clean repo snapshot)

On SUCCESS (in `workspace`, `finalize`, and `finalize_workspace` modes; excluding `--test-mode`), the runner
creates a git-archive success zip in `patches/`. The filename is configurable via
`success_archive_name` / `--success-archive-name` (default `{repo}-{branch}.zip`, e.g. `audiomason2-main.zip`).
It contains only git-tracked files and does not include logs, workspaces, caches, or patch inputs.

---

## Issue diff bundle (SUCCESS: per-file unified diffs + logs)

On SUCCESS (in `workspace`, `finalize`, and `finalize_workspace` modes; excluding `--test-mode`), the runner also creates an issue diff bundle zip under `patches/artifacts/`.

Naming:
- `issue_<ISSUE>_diff.zip`
- If a file already exists, the runner creates `issue_<ISSUE>_diff_v2.zip`, `issue_<ISSUE>_diff_v3.zip`, etc.
- In `finalize` mode (no issue id), the runner uses a pseudo issue id derived from the finalize log filename: `FINALIZE_<ts>`.

Contents:
- `manifest.txt` (issue id, base sha, files list, diff entries list, logs list)
- `diff/` (per-file unified diffs: `diff/<repo-path>.patch`)
- `logs/` (all logs for the issue id; for `finalize`, only the current finalize log)

Diff scope rules:
- In workspace modes, the diff set is limited to `files_to_promote` (the promotion plan), and it includes any gate modifications of those files (for example ruff autofix/format).
- In `finalize`, the diff set is limited to the union of decision paths before gates and changed paths after gates (so ruff changes are included without pulling in unrelated tracked files).


- --gate-badguys-runner {auto,on,off}: runner-only badguys gate (default auto)

## Console color output

The runner can colorize only the OK/FAIL/SUCCESS tokens on stdout.

Configuration:
- Config file key: console_color = "auto"|"always"|"never"
- CLI: --color {auto,always,never} or --no-color
- Env: NO_COLOR disables color regardless of config/CLI
