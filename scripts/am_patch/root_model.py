from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from am_patch.errors import RunnerError


@dataclass(frozen=True)
class RootModel:
    runner_root: Path
    artifacts_root: Path
    active_target_repo_root: Path
    target_repo_roots: tuple[Path, ...]
    patch_root: Path


def _resolve_runner_relative(raw: str | None, *, runner_root: Path) -> Path | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    path = Path(text)
    base = path if path.is_absolute() else (runner_root / path)
    return base.resolve()


def _resolved_registry(raw_values: list[str], *, runner_root: Path) -> tuple[Path, ...]:
    out: list[Path] = []
    seen: set[Path] = set()
    for raw in raw_values:
        resolved = _resolve_runner_relative(raw, runner_root=runner_root)
        if resolved is None or resolved in seen:
            continue
        out.append(resolved)
        seen.add(resolved)
    return tuple(out)


def _resolve_target_selector(
    raw: str | None,
    *,
    runner_root: Path,
    registry: tuple[Path, ...],
) -> Path | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text == "." or text == runner_root.name:
        return runner_root

    named_matches = [entry for entry in registry if entry.name == text]
    if len(named_matches) == 1:
        return named_matches[0]
    if len(named_matches) > 1:
        raise RunnerError(
            "CONFIG",
            "INVALID",
            f"target selector '{text}' matches multiple target_repo_roots entries",
        )

    return _resolve_runner_relative(text, runner_root=runner_root)


def resolve_artifacts_root(policy: object, *, runner_root: Path) -> Path:
    runner_root = runner_root.resolve()
    artifacts_root = _resolve_runner_relative(
        getattr(policy, "artifacts_root", None), runner_root=runner_root
    )
    if artifacts_root is None:
        return runner_root
    return artifacts_root


def resolve_patch_root(policy: object, *, runner_root: Path) -> Path:
    runner_root = runner_root.resolve()
    artifacts_root = resolve_artifacts_root(policy, runner_root=runner_root)
    patch_dir = _resolve_runner_relative(
        getattr(policy, "patch_dir", None), runner_root=runner_root
    )
    patch_dir_name = str(getattr(policy, "patch_dir_name", "patches"))
    if patch_dir is not None:
        return patch_dir
    return artifacts_root / patch_dir_name


def _render_target_registry(
    target_repo_roots: tuple[Path, ...] | list[str] | None,
    *,
    runner_root: Path,
) -> tuple[Path, ...]:
    if target_repo_roots is None:
        return ()
    if isinstance(target_repo_roots, tuple):
        return tuple(path.resolve() for path in target_repo_roots)
    return _resolved_registry(target_repo_roots, runner_root=runner_root)


def render_target_selector(
    *,
    runner_root: Path,
    active_target_repo_root: Path,
    target_repo_roots: tuple[Path, ...] | list[str] | None = None,
) -> str:
    runner_root = runner_root.resolve()
    active_target_repo_root = active_target_repo_root.resolve()
    if active_target_repo_root == runner_root:
        return runner_root.name

    registry = _render_target_registry(target_repo_roots, runner_root=runner_root)

    named_matches = [entry for entry in registry if entry.resolve() == active_target_repo_root]
    if len(named_matches) == 1:
        return named_matches[0].name

    try:
        return active_target_repo_root.relative_to(runner_root).as_posix()
    except ValueError:
        return str(active_target_repo_root)


def resolve_root_model(policy: object, *, runner_root: Path) -> RootModel:
    runner_root = runner_root.resolve()
    artifacts_root = resolve_artifacts_root(policy, runner_root=runner_root)
    registry = _resolved_registry(
        list(getattr(policy, "target_repo_roots", []) or []), runner_root=runner_root
    )
    active_target = _resolve_target_selector(
        getattr(policy, "active_target_repo_root", None),
        runner_root=runner_root,
        registry=registry,
    )
    if active_target is None:
        active_target = _resolve_target_selector(
            getattr(policy, "repo_root", None),
            runner_root=runner_root,
            registry=registry,
        )
    if active_target is None:
        active_target = runner_root

    if active_target != runner_root and active_target not in registry:
        raise RunnerError(
            "CONFIG",
            "INVALID",
            "active_target_repo_root must resolve to runner_root "
            "or an entry from target_repo_roots",
        )

    patch_root = resolve_patch_root(policy, runner_root=runner_root)

    return RootModel(
        runner_root=runner_root,
        artifacts_root=artifacts_root,
        active_target_repo_root=active_target,
        target_repo_roots=registry,
        patch_root=patch_root,
    )
