from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from am_patch.deps import Deps, ListEventSink, OSFileOps, SubprocessResult
from am_patch.model import CLIArgs
from am_patch.plan import build_plan
from am_patch.runner import execute_plan


@dataclass
class FakeRunner:
    calls: list[list[str]]

    def run(self, argv: Sequence[str], *, cwd: Path | None = None) -> SubprocessResult:
        self.calls.append(list(argv))
        return SubprocessResult(returncode=0, stdout="", stderr="")


def test_test_mode_has_no_side_effect_phases(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "scripts" / "am_patch").mkdir(parents=True)
    (repo_root / "tests" / "am_patch").mkdir(parents=True)

    patch = repo_root / "p.patch"
    patch.write_text(
        "diff --git a/x.txt b/x.txt\n"
        "index 0000000..1111111 100644\n"
        "--- a/x.txt\n"
        "+++ b/x.txt\n"
        "@@ -0,0 +1 @@\n"
        "+x\n",
        encoding="utf-8",
    )

    cli = CLIArgs(
        issue_id="801",
        commit_message=None,
        patch_input=str(patch),
        finalize_message=None,
        finalize_workspace=False,
        config_path=None,
        verbosity="normal",
        test_mode=True,
        update_workspace=True,
        unified_patch=None,
    )
    plan = build_plan(repo_root, cli)

    runner = FakeRunner(calls=[])
    events = ListEventSink()
    deps = Deps(runner=runner, fs=OSFileOps(), events=events)

    res = execute_plan(plan, deps=deps)
    assert res.ok is True
    assert res.exit_code == 0

    # Ensure no archive/commit/push phases were executed.
    phase_events = [e for e in events.events if e.startswith("phase_start:")]
    assert "phase_start:archive" not in phase_events
    assert "phase_start:commit" not in phase_events
    assert "phase_start:push" not in phase_events
    assert "phase_start:promote" not in phase_events

    # Ensure workspace was deleted.
    ws_root = repo_root / ".am_patch_workspaces" / "issue_801"
    assert not ws_root.exists()
