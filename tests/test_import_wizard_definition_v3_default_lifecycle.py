"""Issue 111: v3 bootstrap stays opt-in and explicit v2 artifacts now fail closed."""

from __future__ import annotations

from copy import deepcopy
from importlib import import_module
from pathlib import Path

from audiomason.core.config import ConfigResolver

ImportWizardEngine = import_module("plugins.import.engine").ImportWizardEngine
FinalizeError = import_module("plugins.import.errors").FinalizeError
atomic_write_json = import_module("plugins.import.storage").atomic_write_json
load_or_bootstrap_wizard_definition = import_module(
    "plugins.import.wizard_definition_model"
).load_or_bootstrap_wizard_definition
build_default_wizard_definition_v3 = import_module(
    "plugins.import.dsl.default_wizard_v3"
).build_default_wizard_definition_v3
CANONICAL_STEP_ORDER = import_module("plugins.import.flow_runtime").CANONICAL_STEP_ORDER
RootName = import_module("plugins.file_io.service.types").RootName
WIZARD_DEFINITION_REL_PATH = import_module(
    "plugins.import.wizard_definition_model"
).WIZARD_DEFINITION_REL_PATH


def _make_engine(tmp_path: Path) -> ImportWizardEngine:
    roots = {
        name: tmp_path / name for name in ("inbox", "stage", "outbox", "jobs", "config", "wizards")
    }
    for root in roots.values():
        root.mkdir(parents=True, exist_ok=True)
    defaults = {
        "file_io": {
            "roots": {
                "inbox_dir": str(roots["inbox"]),
                "stage_dir": str(roots["stage"]),
                "outbox_dir": str(roots["outbox"]),
                "jobs_dir": str(roots["jobs"]),
                "config_dir": str(roots["config"]),
                "wizards_dir": str(roots["wizards"]),
            }
        },
        "output_dir": str(roots["outbox"]),
        "diagnostics": {"enabled": False},
        "plugins": {
            "import": {
                "cli": {
                    "launcher_mode": "fixed",
                    "default_root": "inbox",
                    "default_path": "",
                    "noninteractive": False,
                    "render": {"nav_ui": "prompt"},
                }
            }
        },
    }
    resolver = ConfigResolver(
        cli_args=defaults,
        defaults=defaults,
        user_config_path=tmp_path / "no_user_config.yaml",
        system_config_path=tmp_path / "no_system_config.yaml",
    )
    return ImportWizardEngine(resolver=resolver)


def _v2_definition() -> dict[str, object]:
    return {
        "version": 2,
        "graph": {
            "entry_step_id": CANONICAL_STEP_ORDER[0],
            "nodes": [{"step_id": sid} for sid in CANONICAL_STEP_ORDER],
            "edges": [
                {
                    "from_step_id": CANONICAL_STEP_ORDER[i],
                    "to_step_id": CANONICAL_STEP_ORDER[i + 1],
                    "priority": 0,
                    "when": None,
                }
                for i in range(len(CANONICAL_STEP_ORDER) - 1)
            ],
        },
    }


def _replace_expr(value: object, *, old: str, new: str) -> object:
    if isinstance(value, dict):
        return {
            key: (new if key == "expr" and item == old else _replace_expr(item, old=old, new=new))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_expr(item, old=old, new=new) for item in value]
    return value


def _legacy_v3_effective_author_definition() -> dict[str, object]:
    definition = deepcopy(build_default_wizard_definition_v3())
    nodes = [
        node
        for node in definition["nodes"]
        if node["step_id"]
        not in {
            "init_author_loop",
            "effective_author_item",
            "store_author_item",
            "author_loop_check",
        }
    ]
    insert_at = (
        next(
            index
            for index, node in enumerate(nodes)
            if node["step_id"] == "metadata_validate_initial"
        )
        + 1
    )
    nodes.insert(
        insert_at,
        {
            "step_id": "effective_author",
            "op": {
                "primitive_id": "ui.prompt_text",
                "primitive_version": 1,
                "inputs": {
                    "label": "Author",
                    "prompt": "[source] Author",
                    "prefill_expr": {"expr": "$.state.vars.phase1.metadata.normalize_author"},
                    "default_expr": {"expr": "$.state.vars.phase1.metadata.author_prompt_prefill"},
                    "help": "Press Enter to keep the suggested author.",
                    "hint_expr": {"expr": "$.state.vars.phase1.metadata.author_prompt_hint"},
                    "examples_expr": {
                        "expr": "$.state.vars.phase1.metadata.author_prompt_examples"
                    },
                },
                "writes": [
                    {
                        "to_path": "$.state.answers.effective_author.author",
                        "value": {"expr": "$.op.outputs.value"},
                    }
                ],
            },
        },
    )
    edges = [
        edge
        for edge in definition["edges"]
        if edge["from"]
        not in {
            "metadata_validate_initial",
            "init_author_loop",
            "effective_author_item",
            "store_author_item",
            "author_loop_check",
        }
        and edge["to"]
        not in {
            "init_author_loop",
            "effective_author_item",
            "store_author_item",
            "author_loop_check",
        }
    ]
    edges.extend(
        [
            {"from": "metadata_validate_initial", "to": "effective_author"},
            {"from": "effective_author", "to": "metadata_validate_after_author"},
        ]
    )
    definition["nodes"] = _replace_expr(
        nodes,
        old="$.state.answers.store_author_item.author",
        new="$.state.answers.effective_author.author",
    )
    definition["edges"] = edges
    return definition


def _legacy_v3_effective_title_definition() -> dict[str, object]:
    definition = deepcopy(build_default_wizard_definition_v3())
    nodes = [
        node
        for node in definition["nodes"]
        if node["step_id"]
        not in {"init_title_loop", "effective_title_item", "store_title_item", "title_loop_check"}
    ]
    insert_at = (
        next(
            index
            for index, node in enumerate(nodes)
            if node["step_id"] == "metadata_validate_after_author"
        )
        + 1
    )
    nodes.insert(
        insert_at,
        {
            "step_id": "effective_title",
            "op": {
                "primitive_id": "ui.prompt_text",
                "primitive_version": 1,
                "inputs": {
                    "label": "Book title",
                    "prompt": "[book] Book title",
                    "prefill_expr": {"expr": "$.state.vars.phase1.metadata.title_prompt_prefill"},
                    "default_expr": {"expr": "$.state.vars.phase1.metadata.title_prompt_prefill"},
                    "help": "Press Enter to keep the suggested title.",
                    "hint_expr": {"expr": "$.state.vars.phase1.metadata.title_prompt_hint"},
                    "examples_expr": {"expr": "$.state.vars.phase1.metadata.title_prompt_examples"},
                },
                "writes": [
                    {
                        "to_path": "$.state.answers.effective_title.title",
                        "value": {"expr": "$.op.outputs.value"},
                    }
                ],
            },
        },
    )
    edges = [
        edge
        for edge in definition["edges"]
        if edge["from"]
        not in {
            "metadata_validate_after_author",
            "init_title_loop",
            "effective_title_item",
            "store_title_item",
            "title_loop_check",
        }
        and edge["to"]
        not in {"init_title_loop", "effective_title_item", "store_title_item", "title_loop_check"}
    ]
    edges.extend(
        [
            {"from": "metadata_validate_after_author", "to": "effective_title"},
            {"from": "effective_title", "to": "metadata_validate_after_title"},
        ]
    )
    definition["nodes"] = _replace_expr(
        nodes,
        old="$.state.answers.store_title_item.title",
        new="$.state.answers.effective_title.title",
    )
    definition["edges"] = edges
    return definition


def test_existing_v2_artifact_keeps_v2_dispatch_while_v3_bootstrap_stays_available(
    tmp_path: Path,
) -> None:
    engine = _make_engine(tmp_path)
    fs = engine.get_file_service()

    atomic_write_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH, _v2_definition())

    loaded = load_or_bootstrap_wizard_definition(fs, bootstrap_default_version=3)
    assert loaded["version"] == 2

    try:
        engine.get_flow_model()
    except FinalizeError as exc:
        assert str(exc) == "catalog missing required step definitions"
    else:
        raise AssertionError("engine.get_flow_model() must fail closed for explicit v2 artifact")

    state = engine.create_session("inbox", "")
    assert state["error"]["code"] == "INVARIANT_VIOLATION"
    assert state["error"]["message"] == "catalog missing required step definitions"


def test_existing_v3_artifact_stays_authoritative_over_bootstrap_seed(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    fs = engine.get_file_service()

    authored = {
        "version": 3,
        "entry_step_id": "pick_author",
        "nodes": [
            {
                "step_id": "pick_author",
                "op": {
                    "primitive_id": "ui.prompt_text",
                    "primitive_version": 1,
                    "inputs": {"label": "Authored label"},
                    "writes": [],
                },
            }
        ],
        "edges": [],
    }
    atomic_write_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH, authored)

    loaded = load_or_bootstrap_wizard_definition(fs, bootstrap_default_version=3)

    assert loaded["version"] == 3
    assert loaded["entry_step_id"] == "pick_author"
    assert loaded["nodes"][0]["op"]["inputs"]["label"] == "Authored label"


def test_legacy_v3_effective_author_artifact_migrates_to_author_loop(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    fs = engine.get_file_service()

    atomic_write_json(
        fs,
        RootName.WIZARDS,
        WIZARD_DEFINITION_REL_PATH,
        _legacy_v3_effective_author_definition(),
    )

    loaded = load_or_bootstrap_wizard_definition(fs, bootstrap_default_version=3)
    node_ids = [node["step_id"] for node in loaded["nodes"]]

    assert loaded["version"] == 3
    assert "effective_author" not in node_ids
    assert {
        "init_author_loop",
        "effective_author_item",
        "store_author_item",
        "author_loop_check",
    }.issubset(set(node_ids))
    metadata_validate_after_author = next(
        node for node in loaded["nodes"] if node["step_id"] == "metadata_validate_after_author"
    )
    assert metadata_validate_after_author["op"]["inputs"]["args"]["author"]["expr"] == (
        "$.state.answers.store_author_item.author"
    )


def test_legacy_v3_effective_title_artifact_migrates_to_title_loop(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    fs = engine.get_file_service()

    atomic_write_json(
        fs,
        RootName.WIZARDS,
        WIZARD_DEFINITION_REL_PATH,
        _legacy_v3_effective_title_definition(),
    )

    loaded = load_or_bootstrap_wizard_definition(fs, bootstrap_default_version=3)
    node_ids = [node["step_id"] for node in loaded["nodes"]]

    assert loaded["version"] == 3
    assert "effective_title" not in node_ids
    assert {
        "init_title_loop",
        "effective_title_item",
        "store_title_item",
        "title_loop_check",
    }.issubset(set(node_ids))
    metadata_validate_after_title = next(
        node for node in loaded["nodes"] if node["step_id"] == "metadata_validate_after_title"
    )
    assert metadata_validate_after_title["op"]["inputs"]["args"]["title"]["expr"] == (
        "$.state.answers.store_title_item.title"
    )
