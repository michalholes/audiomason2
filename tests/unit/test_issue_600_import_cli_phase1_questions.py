from __future__ import annotations

import asyncio
import importlib


def test_issue_600_import_cli_phase1_questions(monkeypatch):
    """Ensure PHASE 1 asks all required questions before PHASE 2 confirm."""

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
        def __init__(self, fs) -> None:  # noqa: ARG002
            return

        def fast_index(self, root, source_root_rel_path):  # noqa: ARG002
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
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def print(self, text: str = "") -> None:  # noqa: ARG002
            return

        def select(self, prompt: str, options: list[str]):  # noqa: ANN001
            self.calls.append(("select", prompt))
            return options[0] if options else None

        def prompt_text(self, prompt: str, default: str):  # noqa: ANN001
            self.calls.append(("prompt_text", prompt))
            return default

        def confirm(self, prompt: str, *, default: bool = False):  # noqa: ANN001, ARG002
            self.calls.append(("confirm", prompt))
            return prompt != "Start processing now?"

    monkeypatch.setattr(mod, "ConfigResolver", _Resolver)
    monkeypatch.setattr(mod, "FileService", _FS)
    monkeypatch.setattr(mod, "PreflightService", _Preflight)
    monkeypatch.setattr(mod, "ImportEngineService", _Engine)

    ui = FakeUI()
    rc = asyncio.run(mod.run_import_cli_flow(argv=[], ui=ui))
    assert rc == 0

    prompts = [p for _, p in ui.calls]
    assert "Effective title" in prompts
    assert "Enable filename normalization?" in prompts
    assert "Enable audio processing?" in prompts
    assert "Select audio processing profile:" in prompts
    assert "Confirm audio processing configuration?" in prompts
    assert "Delete source after import?" in prompts
    assert "Enable delete guard?" in prompts
    assert "Select conflict policy:" in prompts
    assert "Parallelism override (empty = auto)" in prompts

    # Ensure the final PHASE 2 confirmation is asked last.
    last_confirm = [p for m, p in ui.calls if m == "confirm"][-1]
    assert last_confirm == "Start processing now?"
