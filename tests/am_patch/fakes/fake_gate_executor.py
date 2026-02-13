from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from am_patch.deps import SubprocessResult


class PatchApplyError(RuntimeError):
    pass


@dataclass
class PatchApplierFS:
    """A minimal, real filesystem implementation for tests.

    It implements the subset of am_patch.deps.FileOps needed by tests and
    provides a minimal unified-diff applier for 'git apply' simulation.
    """

    def copytree(
        self, src: Path, dst: Path, *, ignore: Any | None = None, dirs_exist_ok: bool = False
    ) -> None:
        import shutil

        shutil.copytree(src, dst, ignore=ignore, dirs_exist_ok=dirs_exist_ok)

    def rmtree(self, path: Path) -> None:
        import shutil

        shutil.rmtree(path, ignore_errors=False)

    def mkdir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def exists(self, path: Path) -> bool:
        return path.exists()

    def apply_unified_diff(self, repo_root: Path, diff_text: str) -> None:
        """Apply a very small subset of unified diffs.

        Supported:
        - exactly one file per diff
        - exactly one hunk
        - hunks that only contain '-' and '+' lines (no context)

        This is sufficient for deterministic unit tests and avoids invoking git.
        """

        rel_path: str | None = None
        for ln in diff_text.splitlines():
            if ln.startswith("+++ b/"):
                rel_path = ln[len("+++ b/") :].strip()
                break
        if not rel_path:
            raise PatchApplyError("missing '+++ b/' line")

        # Parse hunk body.
        hunk_started = False
        removed: list[str] = []
        added: list[str] = []
        for ln in diff_text.splitlines(keepends=True):
            if ln.startswith("@@"):
                hunk_started = True
                continue
            if not hunk_started:
                continue
            if ln.startswith("-"):
                removed.append(ln[1:])
            elif ln.startswith("+"):
                added.append(ln[1:])
            else:
                # Context lines are not supported in this minimal applier.
                raise PatchApplyError(f"unsupported hunk line: {ln!r}")

        path = repo_root / rel_path
        before = path.read_text(encoding="utf-8") if path.exists() else ""
        if before.splitlines(keepends=True) != removed:
            raise PatchApplyError("before-content mismatch")

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(added), encoding="utf-8")


@dataclass
class FakeCommandRunner:
    """A fake CommandRunner that simulates the subset of commands used by the root runner."""

    fs: PatchApplierFS
    default_returncode: int = 0
    failures: dict[tuple[str, ...], SubprocessResult] = field(default_factory=dict)
    calls: list[list[str]] = field(default_factory=list)

    def set_failure(
        self, argv_prefix: Sequence[str], *, stderr: str = "", stdout: str = "", returncode: int = 1
    ) -> None:
        self.failures[tuple(argv_prefix)] = SubprocessResult(
            returncode=returncode, stdout=stdout, stderr=stderr
        )

    def run(self, argv: Sequence[str], *, cwd: Path | None = None) -> SubprocessResult:
        self.calls.append(list(argv))
        cwd = cwd or Path.cwd()

        for prefix, res in self.failures.items():
            if tuple(argv[: len(prefix)]) == prefix:
                return res

        if list(argv[:2]) == ["git", "apply"]:
            patch_path = Path(argv[-1])
            diff_text = patch_path.read_text(encoding="utf-8")
            try:
                self.fs.apply_unified_diff(cwd, diff_text)
            except Exception as e:  # noqa: BLE001
                return SubprocessResult(returncode=1, stdout="", stderr=str(e))
            return SubprocessResult(returncode=0, stdout="", stderr="")

        # All other commands succeed by default.
        return SubprocessResult(returncode=self.default_returncode, stdout="", stderr="")
