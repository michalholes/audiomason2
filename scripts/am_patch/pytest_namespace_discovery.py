from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path

from .pytest_namespace_config import (
    _matches_prefix,
    _namespace_contains,
    _namespace_stem,
    _normalize_path,
    _root_namespaces,
)


class NamespaceMatcher:
    def __init__(
        self,
        *,
        namespace: str,
        path_prefix: str,
        module_prefix: str | None,
    ) -> None:
        self.namespace = _namespace_stem(namespace)
        self.path_prefix = _normalize_path(path_prefix)
        self.module_prefix = module_prefix.strip(".") if module_prefix else None

    def matches_module(self, module_name: str) -> bool:
        if not self.module_prefix:
            return False
        return module_name == self.module_prefix or module_name.startswith(self.module_prefix + ".")

    def matches_text(self, text: str) -> bool:
        if self.path_prefix and self.path_prefix in text:
            return True
        if not self.module_prefix:
            return False
        module = self.module_prefix
        markers = (
            f'"{module}',
            f"'{module}",
            f" {module}.",
            f"from {module}",
            f"import {module}",
            f"({module}",
        )
        return any(marker in text for marker in markers)


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _module_prefix_for_path(path_prefix: str) -> str | None:
    prefix = _normalize_path(path_prefix).rstrip("/")
    if not prefix:
        return None
    if prefix.startswith("plugins/"):
        return prefix.replace("/", ".")
    if prefix == "scripts/am_patch":
        return "am_patch"
    if prefix.startswith("scripts/patchhub"):
        return "patchhub"
    if prefix == "badguys":
        return "badguys"
    if prefix == "src/audiomason/core":
        return "audiomason.core"
    return None


def _test_file_paths(repo_root: Path) -> list[str]:
    tests_root = repo_root / "tests"
    if not tests_root.exists():
        return []
    out: list[str] = []
    for path in sorted(tests_root.rglob("test_*.py")):
        if path.is_file():
            out.append(_normalize_path(str(path.relative_to(repo_root))))
    return out


def _collect_module_references(text: str) -> set[str]:
    refs: set[str] = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return refs

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                refs.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                refs.add(node.module)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "import_module" and node.args:
                arg0 = node.args[0]
                if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                    refs.add(arg0.value)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            if value:
                refs.add(value)
    return refs


def _matcher_defs(
    *,
    roots: Mapping[str, str],
    tree: Mapping[str, str],
) -> tuple[NamespaceMatcher, ...]:
    matchers: dict[str, NamespaceMatcher] = {}
    for raw_namespace, prefix in roots.items():
        namespace = _namespace_stem(raw_namespace)
        if namespace == "*":
            continue
        matchers.setdefault(
            namespace,
            NamespaceMatcher(
                namespace=namespace,
                path_prefix=prefix,
                module_prefix=_module_prefix_for_path(prefix),
            ),
        )
    for namespace, prefix in tree.items():
        matchers[_namespace_stem(namespace)] = NamespaceMatcher(
            namespace=namespace,
            path_prefix=prefix,
            module_prefix=_module_prefix_for_path(prefix),
        )
    ordered = sorted(matchers.values(), key=lambda item: (-len(item.namespace), item.namespace))
    return tuple(ordered)


def _reduce_candidates(candidates: set[str]) -> tuple[str, ...]:
    reduced: list[str] = []
    for candidate in sorted(candidates, key=lambda item: (-len(item), item)):
        if any(_namespace_contains(existing, candidate) for existing in reduced):
            continue
        reduced.append(candidate)
    return tuple(sorted(reduced))


@lru_cache(maxsize=32)
def discover_namespace_ownership(
    repo_root_str: str,
    roots_items: tuple[tuple[str, str], ...],
    tree_items: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    repo_root = Path(repo_root_str)
    roots = dict(roots_items)
    tree = dict(tree_items)
    matchers = _matcher_defs(roots=roots, tree=tree)
    known_roots = set(_root_namespaces(roots))

    ownership: list[tuple[str, tuple[str, ...]]] = []
    for rel_path in _test_file_paths(repo_root):
        text = (repo_root / rel_path).read_text(encoding="utf-8")
        refs = _collect_module_references(text)
        candidates: set[str] = set()
        for matcher in matchers:
            if any(matcher.matches_module(ref) for ref in refs) or matcher.matches_text(text):
                candidates.add(matcher.namespace)
        if not candidates:
            for root in known_roots:
                root_prefix = root + "."
                if any(ref.startswith(root_prefix) for ref in refs):
                    candidates.add(root)
        namespaces = _reduce_candidates(candidates) or ("*",)
        ownership.append((rel_path, namespaces))
    return tuple(ownership)


def select_tests_for_namespaces(
    *,
    ownership: Sequence[tuple[str, Sequence[str]]],
    namespaces: Sequence[str],
    include_descendants: bool,
) -> list[str]:
    targets: list[str] = []
    wanted = [_namespace_stem(item) for item in namespaces if str(item).strip()]
    for rel_path, owned_namespaces in ownership:
        for wanted_namespace in wanted:
            if any(
                _namespace_contains(wanted_namespace, owned)
                if include_descendants
                else _namespace_stem(owned) == wanted_namespace
                for owned in owned_namespaces
            ):
                targets.append(rel_path)
                break
    return targets


def is_direct_test_path(path: str) -> bool:
    norm = _normalize_path(path)
    return (
        _matches_prefix(norm, "tests")
        and Path(norm).name.startswith("test_")
        and norm.endswith(".py")
    )
