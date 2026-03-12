from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from am_patch.pytest_bucket_routing import (  # noqa: E402
    PYTEST_AREA_NAMES_DEFAULT,
    PYTEST_AREA_PREFIXES_DEFAULT,
    PYTEST_AREA_TARGETS_DEFAULT,
    PYTEST_BROAD_REPO_PREFIXES_DEFAULT,
    PYTEST_BROAD_REPO_TARGETS_DEFAULT,
    PYTEST_FAMILY_AREAS_DEFAULT,
    PYTEST_FAMILY_TARGETS_DEFAULT,
    PYTEST_SMOKE_TARGETS_DEFAULT,
    select_pytest_targets,
)


def _routing_policy(mode: str) -> dict[str, object]:
    return {
        "pytest_routing_mode": mode,
        "pytest_smoke_targets": PYTEST_SMOKE_TARGETS_DEFAULT,
        "pytest_area_prefixes": PYTEST_AREA_PREFIXES_DEFAULT,
        "pytest_area_names": PYTEST_AREA_NAMES_DEFAULT,
        "pytest_area_targets": PYTEST_AREA_TARGETS_DEFAULT,
        "pytest_family_areas": PYTEST_FAMILY_AREAS_DEFAULT,
        "pytest_family_targets": PYTEST_FAMILY_TARGETS_DEFAULT,
        "pytest_broad_repo_prefixes": PYTEST_BROAD_REPO_PREFIXES_DEFAULT,
        "pytest_broad_repo_targets": PYTEST_BROAD_REPO_TARGETS_DEFAULT,
    }


def test_legacy_mode_returns_pytest_targets_only() -> None:
    targets = select_pytest_targets(
        decision_paths=["plugins/file_io/service.py"],
        pytest_targets=["tests/custom_a.py", "tests/custom_b.py"],
        routing_policy=_routing_policy("legacy"),
    )
    assert targets == ["tests/custom_a.py", "tests/custom_b.py"]


def test_bucketed_mode_always_includes_smoke_targets() -> None:
    targets = select_pytest_targets(
        decision_paths=["plugins/metadata_googlebooks/service.py"],
        pytest_targets=["tests"],
        routing_policy=_routing_policy("bucketed"),
    )
    assert targets[:2] == PYTEST_SMOKE_TARGETS_DEFAULT


def test_bucketed_mode_selects_leaf_area_targets() -> None:
    targets = select_pytest_targets(
        decision_paths=["plugins/audio_processor/adapter.py"],
        pytest_targets=["tests"],
        routing_policy=_routing_policy("bucketed"),
    )
    assert "tests/test_audio_processor_import_conversion_order.py" in targets


def test_bucketed_mode_selects_import_stack_family_targets() -> None:
    targets = select_pytest_targets(
        decision_paths=["plugins/web_interface/app.py"],
        pytest_targets=["tests"],
        routing_policy=_routing_policy("bucketed"),
    )
    assert "tests/test_import_v3_acceptance_end_to_end.py" in targets


def test_bucketed_mode_selects_observability_cli_family_targets() -> None:
    targets = select_pytest_targets(
        decision_paths=["plugins/syslog/emitter.py"],
        pytest_targets=["tests"],
        routing_policy=_routing_policy("bucketed"),
    )
    assert targets.count("tests/unit/test_cli_diag_command_stub.py") == 1
    assert "tests/unit/test_cli_plugin_command_help.py" in targets


def test_bucketed_mode_selects_tui_stack_family_targets() -> None:
    targets = select_pytest_targets(
        decision_paths=["plugins/tui/app.py"],
        pytest_targets=["tests"],
        routing_policy=_routing_policy("bucketed"),
    )
    assert "tests/unit/test_file_io_service.py" in targets


def test_bucketed_mode_escalates_to_broad_repo_targets() -> None:
    targets = select_pytest_targets(
        decision_paths=["pyproject.toml"],
        pytest_targets=["tests"],
        routing_policy=_routing_policy("bucketed"),
    )
    assert targets[-1] == "tests"


def test_bucketed_mode_escalates_to_broad_repo_targets_for_tests_tree() -> None:
    targets = select_pytest_targets(
        decision_paths=["tests/unit/test_new_case.py"],
        pytest_targets=["tests/legacy_only.py"],
        routing_policy=_routing_policy("bucketed"),
    )
    assert targets[-1] == "tests"
