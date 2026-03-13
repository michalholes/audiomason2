from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence

from .pytest_namespace_config import (
    _matches_prefix,
    _namespace_stem,
    _normalize_dependencies,
    _normalize_full_suite_prefixes,
    _normalize_roots,
    _normalize_tree,
    _root_for_namespace,
)
from .pytest_namespace_discovery import (
    default_repo_root,
    discover_namespace_ownership,
    is_direct_test_path,
    select_tests_for_namespaces,
)


def dedupe_keep_first(items: Sequence[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def match_namespace(
    *,
    path: str,
    roots: Mapping[str, str],
    tree: Mapping[str, str],
) -> str:
    best_namespace = "*"
    best_len = -1
    for namespace, prefix in tree.items():
        if _matches_prefix(path, prefix):
            prefix_len = len(prefix)
            if prefix_len > best_len:
                best_namespace = _namespace_stem(namespace)
                best_len = prefix_len
    if best_namespace != "*":
        return best_namespace

    for raw_namespace, prefix in roots.items():
        namespace = _namespace_stem(raw_namespace)
        if namespace == "*":
            continue
        if _matches_prefix(path, prefix):
            prefix_len = len(prefix)
            if prefix_len > best_len:
                best_namespace = namespace
                best_len = prefix_len
    return best_namespace


def reverse_dependency_closure(dependencies: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    reverse: dict[str, list[str]] = {}
    for dependent, providers in dependencies.items():
        dep_name = _namespace_stem(dependent)
        for provider in providers:
            prov_name = _namespace_stem(provider)
            members = reverse.setdefault(prov_name, [])
            if dep_name not in members:
                members.append(dep_name)

    closure: dict[str, list[str]] = {}
    for provider in reverse:
        seen: set[str] = set()
        queue = deque(reverse.get(provider, []))
        ordered: list[str] = []
        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            ordered.append(current)
            queue.extend(reverse.get(current, []))
        closure[provider] = ordered
    return closure


def namespace_targets(
    *,
    namespace: str,
    dependencies: Mapping[str, Sequence[str]],
    reverse_closure: Mapping[str, Sequence[str]],
    ownership: Sequence[tuple[str, Sequence[str]]],
    roots: Mapping[str, str],
) -> list[str]:
    ns = _namespace_stem(namespace)
    targets = select_tests_for_namespaces(
        ownership=ownership,
        namespaces=[ns],
        include_descendants=False,
    )

    for dependent in reverse_closure.get(ns, []):
        targets.extend(
            select_tests_for_namespaces(
                ownership=ownership,
                namespaces=[dependent],
                include_descendants=True,
            )
        )

    if ns not in dependencies:
        include_descendants = _root_for_namespace(ns, roots) != ns
        subtree = select_tests_for_namespaces(
            ownership=ownership,
            namespaces=[ns],
            include_descendants=include_descendants,
        )
        if subtree:
            targets.extend(subtree)
        else:
            root_namespace = _root_for_namespace(ns, roots)
            if root_namespace != ns:
                targets.extend(
                    select_tests_for_namespaces(
                        ownership=ownership,
                        namespaces=[root_namespace],
                        include_descendants=False,
                    )
                )

    return dedupe_keep_first(targets)


def select_namespace_pytest_targets(
    *,
    decision_paths: Sequence[str],
    pytest_targets: Sequence[str],
    pytest_roots: Mapping[str, str],
    pytest_tree: Mapping[str, str],
    pytest_dependencies: Mapping[str, Sequence[str]],
    pytest_full_suite_prefixes: Sequence[str],
    repo_root=None,
) -> list[str]:
    roots = _normalize_roots(pytest_roots)
    tree = _normalize_tree(pytest_tree)
    dependencies = _normalize_dependencies(pytest_dependencies)
    full_suite_prefixes = _normalize_full_suite_prefixes(pytest_full_suite_prefixes)
    repo_root = default_repo_root() if repo_root is None else repo_root
    ownership = discover_namespace_ownership(
        str(repo_root),
        tuple(sorted(roots.items())),
        tuple(sorted(tree.items())),
    )
    reverse_closure = reverse_dependency_closure(dependencies)

    selected: list[str] = []
    selected.extend(path for path in decision_paths if is_direct_test_path(path))
    if any(
        _matches_prefix(path, prefix) for path in decision_paths for prefix in full_suite_prefixes
    ):
        selected.extend(pytest_targets)
        return dedupe_keep_first(selected)

    matched_namespaces = [
        match_namespace(path=path, roots=roots, tree=tree) for path in decision_paths
    ]
    for namespace in matched_namespaces:
        selected.extend(
            namespace_targets(
                namespace=namespace,
                dependencies=dependencies,
                reverse_closure=reverse_closure,
                ownership=ownership,
                roots=roots,
            )
        )
    return dedupe_keep_first(selected)
