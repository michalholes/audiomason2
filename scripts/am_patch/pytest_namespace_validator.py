from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .pytest_namespace_config import (
    _namespace_stem,
    _normalize_dependencies,
    _normalize_roots,
    _normalize_tree,
    _root_namespaces,
)


@dataclass(frozen=True)
class NamespacePolicyEvidence:
    repo_dependency_edges: dict[str, tuple[str, ...]]
    external_overrides: dict[str, tuple[str, ...]]


def _plugin_tree_namespaces(tree: Mapping[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for namespace, prefix in tree.items():
        if not str(prefix).startswith("plugins/"):
            continue
        leaf = str(prefix).strip("/").split("/")[-1]
        if leaf:
            out[leaf] = _namespace_stem(namespace)
    return out


def _plugin_dirs(repo_root: Path) -> dict[str, Path]:
    plugins_root = repo_root / "plugins"
    if not plugins_root.exists():
        return {}
    out: dict[str, Path] = {}
    for path in sorted(plugins_root.iterdir(), key=lambda item: item.name):
        if path.is_dir() and (path / "plugin.yaml").exists():
            out[path.name] = path
    return out


class _RepoDependencyCollector(ast.NodeVisitor):
    def __init__(self, plugin_names: set[str]) -> None:
        self.plugin_names = plugin_names
        self.dependencies: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._add_module(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self._add_module(node.module)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if node.args:
            arg0 = node.args[0]
            if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                if _call_name(node.func) == "import_module":
                    self._add_module(arg0.value)
                if _call_name(node.func) == "get_plugin":
                    plugin_name = arg0.value.strip()
                    if plugin_name in self.plugin_names:
                        self.dependencies.add(plugin_name)
        self.generic_visit(node)

    def _add_module(self, module_name: str) -> None:
        text = str(module_name).strip()
        if not text.startswith("plugins."):
            return
        parts = text.split(".")
        if len(parts) < 2:
            return
        plugin_name = parts[1]
        if plugin_name in self.plugin_names:
            self.dependencies.add(plugin_name)


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def collect_repo_namespace_dependency_evidence(
    *,
    repo_root: Path,
    tree: Mapping[str, str],
) -> dict[str, tuple[str, ...]]:
    plugin_dirs = _plugin_dirs(repo_root)
    plugin_namespaces = _plugin_tree_namespaces(tree)
    out: dict[str, tuple[str, ...]] = {}
    for plugin_name, plugin_dir in plugin_dirs.items():
        namespace = plugin_namespaces.get(plugin_name)
        if namespace is None:
            continue
        deps: set[str] = set()
        for path in sorted(plugin_dir.rglob("*.py")):
            try:
                tree_obj = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            collector = _RepoDependencyCollector(set(plugin_dirs))
            collector.visit(tree_obj)
            deps.update(plugin for plugin in collector.dependencies if plugin != plugin_name)
        out[namespace] = tuple(
            sorted(
                plugin_namespaces[plugin_name]
                for plugin_name in deps
                if plugin_name in plugin_namespaces
            )
        )
    return out


def derive_external_dependency_overrides(
    *,
    dependencies: Mapping[str, Sequence[str]],
    repo_dependency_edges: Mapping[str, Sequence[str]],
) -> dict[str, tuple[str, ...]]:
    out: dict[str, tuple[str, ...]] = {}
    for namespace, providers in dependencies.items():
        repo_providers = {
            _namespace_stem(item) for item in repo_dependency_edges.get(namespace, ())
        }
        extras = [
            _namespace_stem(provider)
            for provider in providers
            if _namespace_stem(provider) not in repo_providers
        ]
        if extras:
            out[_namespace_stem(namespace)] = tuple(sorted(dict.fromkeys(extras)))
    return out


def validate_namespace_policy(
    *,
    repo_root: Path,
    pytest_roots: Mapping[str, str],
    pytest_tree: Mapping[str, str],
    pytest_dependencies: Mapping[str, Sequence[str]],
    external_overrides: Mapping[str, Sequence[str]] | None = None,
) -> NamespacePolicyEvidence:
    roots = _normalize_roots(pytest_roots)
    tree = _normalize_tree(pytest_tree)
    dependencies = _normalize_dependencies(pytest_dependencies)
    root_namespaces = set(_root_namespaces(roots))
    errors: list[str] = []

    for namespace, prefix in sorted(tree.items()):
        if not (repo_root / prefix).exists():
            errors.append(f"missing_tree_path:{namespace}:{prefix}")

    endpoints = set(tree) | root_namespaces
    for namespace, dependency_providers in sorted(dependencies.items()):
        if namespace not in endpoints:
            errors.append(f"missing_dependency_endpoint:{namespace}")
        for provider in dependency_providers:
            if provider not in endpoints:
                errors.append(f"missing_dependency_endpoint:{namespace}->{provider}")

    plugin_dirs = _plugin_dirs(repo_root)
    plugin_namespaces = _plugin_tree_namespaces(tree)
    for plugin_name in sorted(plugin_dirs):
        expected = f"am2.plugins.{plugin_name}"
        if plugin_namespaces.get(plugin_name) != expected:
            errors.append(f"missing_plugin_namespace:{plugin_name}:{expected}")

    repo_dependency_edges = collect_repo_namespace_dependency_evidence(
        repo_root=repo_root,
        tree=tree,
    )
    for namespace, repo_providers in sorted(repo_dependency_edges.items()):
        declared = {_namespace_stem(item) for item in dependencies.get(namespace, ())}
        for provider in repo_providers:
            if provider not in declared:
                errors.append(f"missing_repo_dependency:{namespace}->{provider}")

    external: dict[str, tuple[str, ...]]
    if external_overrides is None:
        external = derive_external_dependency_overrides(
            dependencies=dependencies,
            repo_dependency_edges=repo_dependency_edges,
        )
    else:
        external = {
            key: tuple(values)
            for key, values in _normalize_dependencies(external_overrides).items()
        }
        for namespace, external_providers in external.items():
            declared = {_namespace_stem(item) for item in dependencies.get(namespace, ())}
            for provider in external_providers:
                if provider not in declared:
                    errors.append(f"undeclared_external_override:{namespace}->{provider}")

    for namespace, external_providers in sorted(external.items()):
        repo_provider_set = {
            _namespace_stem(item) for item in repo_dependency_edges.get(namespace, ())
        }
        for provider in external_providers:
            if provider in repo_provider_set:
                errors.append(f"external_override_conflicts_repo:{namespace}->{provider}")

    if errors:
        raise ValueError("; ".join(errors))

    return NamespacePolicyEvidence(
        repo_dependency_edges={
            namespace: tuple(sorted(dict.fromkeys(providers)))
            for namespace, providers in sorted(repo_dependency_edges.items())
        },
        external_overrides={
            namespace: tuple(sorted(dict.fromkeys(providers)))
            for namespace, providers in sorted(external.items())
        },
    )
