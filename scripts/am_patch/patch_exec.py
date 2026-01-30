from __future__ import annotations

import hashlib
import os
import shutil
import sys
from pathlib import Path

from .errors import RunnerError
from .log import Logger


def precheck_patch_script(path: Path, *, ascii_only: bool) -> None:
    import ast

    if ascii_only:
        raw = path.read_bytes()
        try:
            raw.decode("ascii")
        except UnicodeDecodeError as e:
            raise RunnerError(
                "PREFLIGHT", "PATCH_ASCII", f"patch script contains non-ascii characters: {path}"
            ) from e

    # Must parse cleanly and define FILES at top-level.
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as e:
        raise RunnerError("PREFLIGHT", "PATCH_SYNTAX", f"patch syntax error: {e}") from e

    has_files = any(
        isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "FILES" for t in n.targets)
        for n in tree.body
    )
    if not has_files:
        raise RunnerError(
            "PREFLIGHT", "PATCH_FILES", "patch script must define FILES=[...] at top-level"
        )


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _find_bwrap() -> str | None:
    # Respect explicit override first.
    env = os.environ.get("AM_PATCH_BWRAP")
    if env:
        return env
    return shutil.which("bwrap")


def _build_bwrap_cmd(
    *, workspace_repo: Path, python_argv: list[str], unshare_net: bool
) -> list[str]:
    bwrap = _find_bwrap()
    if not bwrap:
        raise RunnerError(
            "PREFLIGHT", "BWRAP", "bwrap not found (install bubblewrap or disable patch_jail)"
        )

    cmd: list[str] = [bwrap, "--die-with-parent", "--new-session"]

    if unshare_net:
        cmd.append("--unshare-net")

    # Minimal runtime filesystem. Everything is read-only except the workspace repo.
    cmd += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]

    for p in ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc"):
        if Path(p).exists():
            cmd += ["--ro-bind", p, p]

    # Provide a writable repo mount at /repo (the ONLY intended write location).
    cmd += ["--bind", str(workspace_repo), "/repo", "--chdir", "/repo"]

    cmd += ["--"] + python_argv
    return cmd


def run_patch(
    logger: Logger,
    patch_script: Path,
    *,
    workspace_repo: Path,
    policy: object,
) -> None:
    # Copy patch into workspace and execute the copied script so __file__ is inside the workspace.
    # This prevents accidental writes to the live repo based on Path(__file__).
    src = patch_script.resolve()
    data = src.read_bytes()
    digest = _sha256_bytes(data)

    exec_path = (workspace_repo / ".am_patch" / "patch_exec.py").resolve()
    _write_atomic(exec_path, data)

    logger.section("PATCH SOURCE")
    logger.line(f"patch_source_path={src}")
    logger.line(f"patch_source_sha256={digest}")

    logger.section("PATCH EXEC (PREP)")
    logger.line(f"patch_exec_path={exec_path}")
    logger.line(f"patch_jail={getattr(policy, 'patch_jail', False)}")

    # Build command (optionally inside a jail).
    if getattr(policy, "patch_jail", False):
        # Inside jail we intentionally run system python3, not the runner's interpreter,
        # so that the jail does not need access to any venv under the live repo.
        python_argv = ["python3", f"/repo/{exec_path.relative_to(workspace_repo)}"]
        cmd = _build_bwrap_cmd(
            workspace_repo=workspace_repo,
            python_argv=python_argv,
            unshare_net=getattr(policy, "patch_jail_unshare_net", True),
        )
        logger.section("PATCH EXEC (JAILED)")
        logger.line("cmd=" + " ".join(cmd))
        r = logger.run_logged(cmd, cwd=workspace_repo)
    else:
        logger.section("PATCH EXEC")
        r = logger.run_logged([sys.executable, str(exec_path)], cwd=workspace_repo)

    if r.returncode != 0:
        raise RunnerError("PATCH", "INTERNAL", f"patch script failed (rc={r.returncode})")
