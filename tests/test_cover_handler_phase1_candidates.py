"""Issue 123: cover_handler candidate discovery and apply surfaces."""

from __future__ import annotations

import asyncio
from pathlib import Path

from plugins.cover_handler.plugin import CoverHandlerPlugin


def test_discover_cover_candidates_orders_named_generic_and_embedded(tmp_path: Path) -> None:
    plugin = CoverHandlerPlugin()
    source_dir = tmp_path / "book"
    source_dir.mkdir()
    for name in ["folder.png", "cover.jpeg", "zzz.jpg", "aaa.webp"]:
        (source_dir / name).write_bytes(name.encode("utf-8"))
    audio_file = source_dir / "book.m4a"
    audio_file.write_bytes(b"audio")

    candidates = plugin.discover_cover_candidates(source_dir, audio_file=audio_file)

    ordered = [(item["kind"], Path(item["path"]).name, item["apply_mode"]) for item in candidates]
    assert ordered == [
        ("file", "cover.jpeg", "copy"),
        ("file", "folder.png", "copy"),
        ("file", "aaa.webp", "copy"),
        ("file", "zzz.jpg", "copy"),
        ("embedded", "book.m4a", "extract_embedded"),
    ]


def test_discover_cover_candidates_embedded_only_when_no_file_cover(tmp_path: Path) -> None:
    plugin = CoverHandlerPlugin()
    source_dir = tmp_path / "book"
    source_dir.mkdir()
    audio_file = source_dir / "book.mp3"
    audio_file.write_bytes(b"audio")

    candidates = plugin.discover_cover_candidates(source_dir, audio_file=audio_file)

    assert candidates == [
        {
            "kind": "embedded",
            "candidate_id": "embedded:book.mp3",
            "apply_mode": "extract_embedded",
            "path": str(audio_file),
        }
    ]


def test_build_embedded_extract_commands_for_m4a_has_fallback(tmp_path: Path) -> None:
    plugin = CoverHandlerPlugin()
    audio_file = tmp_path / "book.m4a"
    output = tmp_path / "cover.jpg"

    commands = plugin.build_embedded_extract_commands(audio_file, output)

    assert len(commands) == 2
    assert commands[0][-3:] == ["-c:v", "copy", str(output)]
    assert commands[1][-4:] == ["-map", "0:v:0", "-frames:v", "1", str(output)][-4:]


def test_apply_cover_candidate_copies_file_to_output_dir(tmp_path: Path) -> None:
    plugin = CoverHandlerPlugin()
    source = tmp_path / "cover.png"
    source.write_bytes(b"cover-bytes")
    output_dir = tmp_path / "out"

    copied = asyncio.run(
        plugin.apply_cover_candidate(
            {
                "kind": "file",
                "candidate_id": "file:cover.png",
                "apply_mode": "copy",
                "path": str(source),
            },
            output_dir=output_dir,
        )
    )

    assert copied == output_dir / "cover.png"
    assert copied is not None
    assert copied.read_bytes() == b"cover-bytes"
