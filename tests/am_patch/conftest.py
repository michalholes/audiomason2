from __future__ import annotations

import importlib.util
import io
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest
from am_patch.deps import Deps, ListEventSink


def _load_fakes() -> tuple[type[object], type[object]]:
    """Load fakes without turning tests/am_patch into an importable 'am_patch' package."""

    p = Path(__file__).resolve().parent / "fakes" / "fake_gate_executor.py"
    spec = importlib.util.spec_from_file_location("_am_patch_test_fakes_gate", p)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)  # type: ignore[assignment]
    return mod.FakeCommandRunner, mod.PatchApplierFS


FakeCommandRunner, PatchApplierFS = _load_fakes()


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "am_patch").mkdir()
    (root / "tests" / "am_patch").mkdir(parents=True)
    # A file used by most tests.
    (root / "x.txt").write_text("one\n", encoding="utf-8")
    # Git metadata should never be copied into a workspace.
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    return root


@pytest.fixture()
def fake_deps(repo_root: Path) -> Deps:
    fs = PatchApplierFS()
    runner = FakeCommandRunner(fs=fs)
    return Deps(runner=runner, fs=fs, events=ListEventSink())


@pytest.fixture()
def make_patch_zip(tmp_path: Path) -> Callable[[str, str], Path]:
    def _make(rel_path: str, unified_diff: str) -> Path:
        p = tmp_path / "p.zip"
        with zipfile.ZipFile(p, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr(f"patches/per_file/{rel_path.replace('/', '__')}.patch", unified_diff)
        return p

    return _make


@pytest.fixture()
def make_unified_patch() -> Callable[[str, str, str], str]:
    """Return a minimal unified diff replacing file content.

    This helper intentionally generates a single-hunk patch. It is sufficient
    for exercising the root runner without relying on git.
    """

    def _make(rel_path: str, before: str, after: str) -> str:
        before_lines = before.splitlines(keepends=True)
        after_lines = after.splitlines(keepends=True)

        out = io.StringIO()
        out.write(f"diff --git a/{rel_path} b/{rel_path}\n")
        out.write("index 0000000..1111111 100644\n")
        out.write(f"--- a/{rel_path}\n")
        out.write(f"+++ b/{rel_path}\n")
        out.write(f"@@ -1,{len(before_lines)} +1,{len(after_lines)} @@\n")
        for ln in before_lines:
            out.write(f"-{ln}")
        for ln in after_lines:
            out.write(f"+{ln}")
        return out.getvalue()

    return _make
