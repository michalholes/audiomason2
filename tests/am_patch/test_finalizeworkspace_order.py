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


def test_finalize_workspace_order(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "scripts" / "am_patch").mkdir(parents=True)
    (repo_root / "tests" / "am_patch").mkdir(parents=True)

    patch = repo_root / "p.patch"
    patch.write_text("not a real patch\n", encoding="utf-8")

    cli = CLIArgs(
        issue_id="801",
        commit_message="Issue 801",
        patch_input=str(patch),
        finalize_message=None,
        finalize_workspace=True,
        config_path=None,
        verbosity="normal",
        test_mode=False,
        update_workspace=True,
        unified_patch=None,
    )
    plan = build_plan(repo_root, cli)

    runner = FakeRunner(calls=[])
    events = ListEventSink()
    deps = Deps(runner=runner, fs=OSFileOps(), events=events)

    res = execute_plan(plan, deps=deps)
    assert res.ok is True

    starts = [e for e in events.events if e.startswith("phase_start:")]
    # expected order (subset)
    want = [
        "phase_start:workspace",
        "phase_start:patch",
        "phase_start:gates_workspace",
        "phase_start:promote",
        "phase_start:gates_live",
        "phase_start:archive",
        "phase_start:commit",
        "phase_start:push",
        "phase_start:cleanup",
    ]
    idx = 0
    for w in want:
        while idx < len(starts) and starts[idx] != w:
            idx += 1
        assert idx < len(starts), f"missing phase start: {w}"
