from __future__ import annotations

from importlib import import_module

build_phase1_source_projection = import_module(
    "plugins.import.phase1_source_intake"
).build_phase1_source_projection


def _state() -> dict[str, object]:
    return {
        "source": {"root": "inbox", "relative_path": ""},
        "answers": {},
        "computed": {},
        "conflicts": {},
    }


def test_phase1_selection_ignores_books_with_only_zero_byte_audio() -> None:
    discovery = [
        {"kind": "dir", "relative_path": "Author/Book"},
        {"kind": "file", "relative_path": "Author/Book/track.mp3", "size": 0},
        {"kind": "file", "relative_path": "Author/Book/lic.jpg", "size": 1024},
    ]

    projection = build_phase1_source_projection(discovery=discovery, state=_state())

    assert projection["select_authors"]["ordered_ids"] == []
    assert projection["select_books"]["ordered_ids"] == []
    assert projection["select_books"]["filtered_ids"] == []


def test_phase1_selection_keeps_books_when_audio_size_is_unknown() -> None:
    discovery = [
        {"kind": "dir", "relative_path": "Author/Book"},
        {"kind": "file", "relative_path": "Author/Book/track.mp3"},
    ]

    projection = build_phase1_source_projection(discovery=discovery, state=_state())

    assert len(projection["select_authors"]["ordered_ids"]) == 1
    assert len(projection["select_books"]["ordered_ids"]) == 1
    assert projection["select_books"]["selected_source_relative_paths"] == ["Author/Book"]


def test_phase1_selection_includes_nonempty_bundle_as_book() -> None:
    discovery = [
        {"kind": "dir", "relative_path": "Author/Book"},
        {"kind": "file", "relative_path": "Author/Book/track.mp3", "size": 10},
        {"kind": "bundle", "relative_path": "sp.rar", "size": 1024},
    ]

    projection = build_phase1_source_projection(discovery=discovery, state=_state())

    selected_paths = projection["select_books"]["selected_source_relative_paths"]
    assert "Author/Book" in selected_paths
    assert "sp.rar" in selected_paths
