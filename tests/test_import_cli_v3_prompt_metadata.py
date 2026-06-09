"""Issue 109: CLI renderer parity for v3 prompt metadata."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

_collect_v3_prompt_payload = import_module("plugins.import.cli_renderer")._collect_v3_prompt_payload

PROMPT_STEP: dict[str, object] = {
    "primitive_id": "ui.prompt_text",
    "primitive_version": 1,
}

PROMPT_METADATA: dict[str, object] = {
    "label": "Display name",
    "prompt": "Enter the final display name",
    "help": "CLI and Web must render the same metadata",
    "hint": "Press Enter to accept the backend prefill",
    "examples": ["Ada", "Grace"],
    "prefill": "Ada",
}

PROMPT_STEP_NO_DEFAULT: dict[str, object] = {
    "primitive_id": "ui.prompt_text",
    "primitive_version": 1,
}

PROMPT_METADATA_NO_DEFAULT: dict[str, object] = {
    "label": "Display name",
    "prompt": "Enter an optional display name",
    "help": "Blank Enter should keep the value unset",
}


class _FakeEngine:
    pass


def test_cli_renderer_renders_v3_prompt_metadata_and_accepts_prefill(
    tmp_path: Path,
) -> None:
    del tmp_path
    printed: list[str] = []
    inputs = iter([""])

    def _input_fn(_prompt: str) -> str:
        return next(inputs)

    payload, rc = _collect_v3_prompt_payload(
        engine=_FakeEngine(),
        session_id="session",
        step=PROMPT_STEP,
        metadata=PROMPT_METADATA,
        input_fn=_input_fn,
        print_fn=printed.append,
        confirm_defaults=True,
        allow_inline=False,
    )

    assert rc is None
    joined = "\n".join(printed)
    assert "Display name" in joined
    assert "Enter the final display name" in joined
    assert "CLI and Web must render the same metadata" in joined
    assert "Note: Press Enter to accept the backend prefill" in joined
    assert "Examples:" in joined
    assert "Suggested: Ada" in joined
    assert payload == {"value": "Ada"}


def test_cli_renderer_prefill_dict_preserves_unicode_rendering() -> None:
    rendered = import_module("plugins.import.cli_renderer")._stringify_prompt_value(
        {
            "author": "Meyrink, Gustav",
            "title": "Obrazy vepsan\u00e9 do vzduchu",
        }
    )

    assert '"title": "Obrazy vepsan\u00e9 do vzduchu"' in rendered
    assert "\\u00e1" not in rendered
    assert "\\u00e9" not in rendered


def test_cli_renderer_blank_enter_without_seed_submits_null(
    tmp_path: Path,
) -> None:
    del tmp_path
    printed: list[str] = []
    inputs = iter([""])

    def _input_fn(_prompt: str) -> str:
        return next(inputs)

    payload, rc = _collect_v3_prompt_payload(
        engine=_FakeEngine(),
        session_id="session",
        step=PROMPT_STEP_NO_DEFAULT,
        metadata=PROMPT_METADATA_NO_DEFAULT,
        input_fn=_input_fn,
        print_fn=printed.append,
        confirm_defaults=True,
        allow_inline=False,
    )

    assert rc is None
    joined = "\n".join(printed)
    assert "Suggested:" not in joined
    assert payload == {"value": None}
