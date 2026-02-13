from __future__ import annotations

import importlib.util
from pathlib import Path

from am_patch.deps import Deps, ListEventSink
from am_patch.model import CLIArgs, Phase
from am_patch.plan import build_plan
from am_patch.runner import execute_plan


def _load_fakes() -> tuple[type[object], type[object]]:
    p = Path(__file__).resolve().parent / "fakes" / "fake_gate_executor.py"
    spec = importlib.util.spec_from_file_location("_am_patch_test_fakes_gate2", p)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)  # type: ignore[assignment]
    return mod.FakeCommandRunner, mod.PatchApplierFS


FakeCommandRunner, PatchApplierFS = _load_fakes()


def _deps() -> tuple[Deps, FakeCommandRunner, ListEventSink]:
    fs = PatchApplierFS()
    runner = FakeCommandRunner(fs=fs)
    events = ListEventSink()
    return Deps(runner=runner, fs=fs, events=events), runner, events


def test_golden_phase_trace_finalize_workspace(tmp_path: Path) -> None:
    # Create a minimal repo.
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "scripts" / "am_patch").mkdir(parents=True)
    (repo_root / "tests" / "am_patch").mkdir(parents=True)
    (repo_root / "x.txt").write_text("one\n", encoding="utf-8")

    # Patch changes x.txt.
    patch = repo_root / "p.patch"
    patch.write_text(
        "diff --git a/x.txt b/x.txt\n"
        "index 0000000..1111111 100644\n"
        "--- a/x.txt\n"
        "+++ b/x.txt\n"
        "@@ -1,1 +1,1 @@\n"
        "-one\n"
        "+two\n",
        encoding="utf-8",
    )

    deps, _runner, events = _deps()

    cli = CLIArgs(
        issue_id="802",
        commit_message="Issue 802: test",
        patch_input=str(patch),
        finalize_message=None,
        finalize_workspace=True,
        config_path=None,
        verbosity="normal",
        test_mode=False,
        update_workspace=False,
        unified_patch=None,
    )

    plan = build_plan(repo_root, cli)
    assert plan.mode == "finalize_workspace"

    # Golden phase sequence for finalize-workspace (non-test-mode).
    assert plan.phases == (
        Phase.PREFLIGHT,
        Phase.WORKSPACE,
        Phase.PATCH,
        Phase.GATES_WORKSPACE,
        Phase.PROMOTE,
        Phase.GATES_LIVE,
        Phase.ARCHIVE,
        Phase.COMMIT,
        Phase.PUSH,
        Phase.CLEANUP,
    )

    res = execute_plan(plan, deps=deps)
    assert res.ok is True
    assert (repo_root / "x.txt").read_text(encoding="utf-8") == "two\n"

    # Ensure start/end events are emitted deterministically.
    assert events.events[0].startswith("run_start")
    assert events.events[-1].startswith("run_end")


def test_test_mode_always_cleans_workspace_on_failure(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "scripts" / "am_patch").mkdir(parents=True)
    (repo_root / "tests" / "am_patch").mkdir(parents=True)
    (repo_root / "x.txt").write_text("one\n", encoding="utf-8")

    # Patch expects 'one' but file content differs in workspace, forcing patch failure.
    (repo_root / "x.txt").write_text("DIFFERS\n", encoding="utf-8")

    patch = repo_root / "p.patch"
    patch.write_text(
        "diff --git a/x.txt b/x.txt\n"
        "index 0000000..1111111 100644\n"
        "--- a/x.txt\n"
        "+++ b/x.txt\n"
        "@@ -1,1 +1,1 @@\n"
        "-one\n"
        "+two\n",
        encoding="utf-8",
    )

    deps, _runner, _events = _deps()
    cli = CLIArgs(
        issue_id="802",
        commit_message=None,
        patch_input=str(patch),
        finalize_message=None,
        finalize_workspace=False,
        config_path=None,
        verbosity="normal",
        test_mode=True,
        update_workspace=False,
        unified_patch=None,
    )
    plan = build_plan(repo_root, cli)

    res = execute_plan(plan, deps=deps)
    assert res.ok is False
    assert res.exit_code == 2

    ws_root = repo_root / ".am_patch_workspaces" / "issue_802"
    assert not ws_root.exists()
