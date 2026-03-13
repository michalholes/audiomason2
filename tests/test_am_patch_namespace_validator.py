from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from am_patch.pytest_namespace_config import (  # noqa: E402
    PYTEST_DEPENDENCIES_DEFAULT,
    PYTEST_ROOTS_DEFAULT,
    PYTEST_TREE_DEFAULT,
)
from am_patch.pytest_namespace_validator import (  # noqa: E402
    validate_namespace_policy,
)


def test_namespace_validator_accepts_shipped_policy() -> None:
    evidence = validate_namespace_policy(
        repo_root=REPO_ROOT,
        pytest_roots=PYTEST_ROOTS_DEFAULT,
        pytest_tree=PYTEST_TREE_DEFAULT,
        pytest_dependencies=PYTEST_DEPENDENCIES_DEFAULT,
    )
    assert evidence.repo_dependency_edges["am2.plugins.import"] == (
        "am2.plugins.audio_processor",
        "am2.plugins.cover_handler",
        "am2.plugins.file_io",
        "am2.plugins.id3_tagger",
        "am2.plugins.metadata_openlibrary",
    )
    assert evidence.repo_dependency_edges["am2.plugins.web_interface"] == (
        "am2.plugins.file_io",
        "am2.plugins.import",
    )
    assert evidence.external_overrides["am2.plugins.import"] == (
        "am2.plugins.cmd_interface",
        "am2.plugins.daemon",
        "am2.plugins.diagnostics_console",
        "am2.plugins.metadata_googlebooks",
        "am2.plugins.syslog",
        "am2.plugins.text_utils",
        "am2.plugins.web_interface",
    )


def test_namespace_validator_fails_for_missing_plugin_namespace() -> None:
    broken_tree = dict(PYTEST_TREE_DEFAULT)
    broken_tree.pop("am2.plugins.web_interface")
    try:
        validate_namespace_policy(
            repo_root=REPO_ROOT,
            pytest_roots=PYTEST_ROOTS_DEFAULT,
            pytest_tree=broken_tree,
            pytest_dependencies=PYTEST_DEPENDENCIES_DEFAULT,
        )
    except ValueError as exc:
        assert "missing_plugin_namespace:web_interface:am2.plugins.web_interface" in str(exc)
    else:
        raise AssertionError("expected validator to fail for missing plugin namespace")


def test_namespace_validator_fails_for_missing_repo_dependency_edge() -> None:
    broken_deps = {key: list(values) for key, values in PYTEST_DEPENDENCIES_DEFAULT.items()}
    broken_deps["am2.plugins.web_interface"] = ["am2.plugins.import"]
    try:
        validate_namespace_policy(
            repo_root=REPO_ROOT,
            pytest_roots=PYTEST_ROOTS_DEFAULT,
            pytest_tree=PYTEST_TREE_DEFAULT,
            pytest_dependencies=broken_deps,
        )
    except ValueError as exc:
        assert "missing_repo_dependency:am2.plugins.web_interface->am2.plugins.file_io" in str(exc)
    else:
        raise AssertionError("expected validator to fail for missing repo dependency")


def test_namespace_validator_fails_when_external_override_conflicts_with_repo_evidence() -> None:
    try:
        validate_namespace_policy(
            repo_root=REPO_ROOT,
            pytest_roots=PYTEST_ROOTS_DEFAULT,
            pytest_tree=PYTEST_TREE_DEFAULT,
            pytest_dependencies=PYTEST_DEPENDENCIES_DEFAULT,
            external_overrides={"am2.plugins.web_interface": ["am2.plugins.import"]},
        )
    except ValueError as exc:
        assert (
            "external_override_conflicts_repo:am2.plugins.web_interface->am2.plugins.import"
        ) in str(exc)
    else:
        raise AssertionError("expected validator to reject mixed repo and external evidence")
