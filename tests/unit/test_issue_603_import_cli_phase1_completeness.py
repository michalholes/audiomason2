from __future__ import annotations

import asyncio
import importlib


def _is_subsequence(seq: list[str], subseq: list[str]) -> bool:
    it = iter(seq)
    try:
        for x in subseq:
            while True:
                v = next(it)
                if v == x:
                    break
        return True
    except StopIteration:
        return False


def test_issue_603_import_cli_phase1_completeness_and_branching(monkeypatch):
    """Issue 603: PHASE 1 asks all required questions in order and branches correctly."""

    mod = importlib.import_module("plugins.import.cli_flow.flow")

    class _Book:
        def __init__(self) -> None:
            self.author = "Author A"
            self.rel_path = "Author A/Book B"
            self.book_ref = "ref"
            self.unit_type = "dir"
            self.book = "Book B"

    class _Idx:
        def __init__(self) -> None:
            self.authors = ["Author A"]
            self.books = [_Book()]

    class _Lookup:
        def __init__(self) -> None:
            self.status = "unknown"
            self.source = ""
            self.error = ""

    class _Plan:
        def __init__(self) -> None:
            self.proposed_author = "Author A"
            self.proposed_title = "Book B"
            self.lookup = _Lookup()
            self.rename_preview = {"a.mp3": "b.mp3"}

    class _Preflight:
        def __init__(self, fs, *, enable_lookup: bool = True, **kwargs) -> None:  # noqa: ANN001, ARG002
            self._enable_lookup = bool(enable_lookup)

        def fast_index(self, root, source_root_rel_path):  # noqa: ANN001, ARG002
            return _Idx()

        def plan_preview_for_book(self, *args, **kwargs):  # noqa: ANN001, ARG002
            return _Plan()

    class _Engine:
        def __init__(self, fs) -> None:  # noqa: ARG002
            raise AssertionError("PHASE 2 must not start in this test")

    class _FS:
        @staticmethod
        def from_resolver(resolver):  # noqa: ANN001, ARG002
            return object()

    class _Resolver:
        def __init__(self, *args, **kwargs):  # noqa: ANN001, ARG002
            return

    class FakeUI:
        def __init__(self, *, audio_enabled: bool) -> None:
            self.audio_enabled = bool(audio_enabled)
            self.calls: list[tuple[str, str]] = []

        def print(self, text: str = "") -> None:  # noqa: ARG002
            return

        def select(self, prompt: str, options: list[str], default_index: int = 1):  # noqa: ANN001, ARG002
            self.calls.append(("select", prompt))
            return options[0] if options else None

        def prompt_text(self, prompt: str, default: str):  # noqa: ANN001
            self.calls.append(("prompt_text", prompt))
            return default

        def confirm(self, prompt: str, *, default: bool = False):  # noqa: ANN001, ARG002
            self.calls.append(("confirm", prompt))
            if prompt == "Enable audio processing?":
                return self.audio_enabled
            if prompt == "Start processing now?":
                return False
            # For any confirmations during the audio submenu, keep them False by default
            # unless audio is enabled (covered by a separate run below).
            if not self.audio_enabled and prompt in {
                "Enable loudnorm?",
                "Enable bitrate change?",
                "Confirm audio processing configuration?",
            }:
                return False
            return default

    monkeypatch.setattr(mod, "ConfigResolver", _Resolver)
    monkeypatch.setattr(mod, "FileService", _FS)
    monkeypatch.setattr(mod, "PreflightService", _Preflight)
    monkeypatch.setattr(mod, "ImportEngineService", _Engine)

    # Run 1: audio disabled -> must NOT enter audio submenu.
    ui = FakeUI(audio_enabled=False)
    rc = asyncio.run(mod.run_import_cli_flow(argv=[], ui=ui))
    assert rc == 0

    prompts = [p for _, p in ui.calls]

    required_in_order = [
        "Select work mode:",
        "Enable lookup (public DB)?",
        "Select author:",
        "Select book:",
        "Effective author",
        "Effective title",
        "Enable filename normalization?",
        "Filename normalization strategy:",
        "Filename padding:",
        "Filename strictness:",
        "Output filename character policy:",
        "Covers policy:",
        "Wipe ID3 tags before writing new metadata?",
        "Enable audio processing?",
        "Publish book after processing?",
        "Delete source after import?",
        "Select conflict policy:",
        "Parallelism override (empty = auto)",
        "Start processing now?",
    ]

    assert _is_subsequence(prompts, required_in_order)

    # Ensure no audio submenu prompts when disabled.
    assert "Select audio processing profile:" not in prompts
    assert "Enable loudnorm?" not in prompts
    assert "Enable bitrate change?" not in prompts
    assert "Bitrate kbps" not in prompts
    assert "Bitrate mode:" not in prompts
    assert "Confirm audio processing configuration?" not in prompts

    # Ensure the final PHASE 2 confirmation is asked last.
    last_confirm = [p for m, p in ui.calls if m == "confirm"][-1]
    assert last_confirm == "Start processing now?"

    # Run 2: audio enabled -> audio submenu prompts must appear.
    ui2 = FakeUI(audio_enabled=True)
    rc2 = asyncio.run(mod.run_import_cli_flow(argv=[], ui=ui2))
    assert rc2 == 0

    prompts2 = [p for _, p in ui2.calls]
    assert "Select audio processing profile:" in prompts2
    assert "Enable loudnorm?" in prompts2
    assert "Enable bitrate change?" in prompts2
    assert "Confirm audio processing configuration?" in prompts2
