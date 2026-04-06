"""Issue 138: cover_handler parity candidate surfaces."""

from __future__ import annotations

import asyncio
from pathlib import Path

from mutagen.id3 import APIC, ID3
from plugins.cover_handler.plugin import CoverHandlerPlugin
from plugins.file_io.plugin import FileIOPlugin


def _write_mp3(path: Path, *, with_artwork: bool) -> None:
    tags = ID3()
    if with_artwork:
        tags.add(
            APIC(
                encoding=3,
                mime="image/jpeg",
                type=3,
                desc="cover",
                data=b"jpeg-data",
            )
        )
    tags.save(path)


def test_discover_cover_candidates_primary_only_ordering(tmp_path: Path) -> None:
    plugin = CoverHandlerPlugin()
    source_dir = tmp_path / "book"
    source_dir.mkdir()
    for name in ["folder.png", "cover.jpeg", "zzz.jpg", "aaa.webp"]:
        (source_dir / name).write_bytes(name.encode("utf-8"))

    candidates = plugin.discover_cover_candidates(source_dir)

    ordered = [(item["kind"], Path(item["path"]).name, item["apply_mode"]) for item in candidates]
    assert ordered == [
        ("file", "cover.jpeg", "copy"),
        ("file", "folder.png", "copy"),
        ("file", "aaa.webp", "copy"),
        ("file", "zzz.jpg", "copy"),
    ]


def test_discover_cover_candidates_fallback_only_ordering(tmp_path: Path) -> None:
    plugin = CoverHandlerPlugin()
    source_dir = tmp_path / "Author" / "Book"
    source_dir.mkdir(parents=True)
    parent_dir = source_dir.parent
    for name in ["folder.png", "cover.jpeg", "zzz.jpg", "aaa.webp"]:
        (parent_dir / name).write_bytes(name.encode("utf-8"))

    candidates = plugin.discover_cover_candidates(source_dir)

    assert [Path(item["path"]).name for item in candidates] == [
        "cover.jpeg",
        "folder.png",
        "aaa.webp",
        "zzz.jpg",
    ]


def test_discover_cover_candidates_orders_primary_before_fallback(tmp_path: Path) -> None:
    plugin = CoverHandlerPlugin()
    source_dir = tmp_path / "Author" / "Book"
    source_dir.mkdir(parents=True)
    parent_dir = source_dir.parent
    (source_dir / "folder.png").write_bytes(b"primary")
    (parent_dir / "cover.jpeg").write_bytes(b"fallback-named")
    (parent_dir / "zzz.jpg").write_bytes(b"fallback-generic")

    candidates = plugin.discover_cover_candidates(source_dir)

    assert [Path(item["path"]).name for item in candidates] == [
        "folder.png",
        "cover.jpeg",
        "zzz.jpg",
    ]


def test_discover_cover_candidates_appends_embedded_only_after_positive_probe(
    tmp_path: Path,
) -> None:
    plugin = CoverHandlerPlugin()
    source_dir = tmp_path / "book"
    source_dir.mkdir()
    (source_dir / "cover.jpeg").write_bytes(b"cover")
    audio_file = source_dir / "book.mp3"
    _write_mp3(audio_file, with_artwork=True)

    candidates = plugin.discover_cover_candidates(source_dir, audio_file=audio_file)

    assert [(item["kind"], Path(item["path"]).name) for item in candidates] == [
        ("file", "cover.jpeg"),
        ("embedded", "book.mp3"),
    ]
    assert candidates[-1]["cache_key"] == "embedded:book.mp3"


def test_discover_cover_candidates_skips_embedded_without_artwork(tmp_path: Path) -> None:
    plugin = CoverHandlerPlugin()
    source_dir = tmp_path / "book"
    source_dir.mkdir()
    audio_file = source_dir / "book.mp3"
    _write_mp3(audio_file, with_artwork=False)

    candidates = plugin.discover_cover_candidates(source_dir, audio_file=audio_file)

    assert candidates == []


def test_discover_cover_candidates_disambiguates_duplicate_basenames_across_scopes(
    tmp_path: Path,
) -> None:
    plugin = CoverHandlerPlugin()
    source_dir = tmp_path / "Author" / "Book"
    source_dir.mkdir(parents=True)
    parent_dir = source_dir.parent
    (source_dir / "cover.jpeg").write_bytes(b"primary")
    (parent_dir / "cover.jpeg").write_bytes(b"fallback")

    candidates = plugin.discover_cover_candidates(source_dir)

    assert [item["candidate_id"] for item in candidates] == [
        "file:cover.jpeg",
        "file:cover.jpeg@fallback",
    ]
    assert [item["cache_key"] for item in candidates] == [
        "file:cover.jpeg",
        "file:cover.jpeg@fallback",
    ]


def test_discover_cover_candidates_disambiguates_case_variant_duplicates_in_same_scope(
    tmp_path: Path,
) -> None:
    plugin = CoverHandlerPlugin()
    source_dir = tmp_path / "book"
    source_dir.mkdir()
    (source_dir / "cover.jpeg").write_bytes(b"lower")
    (source_dir / "COVER.JPEG").write_bytes(b"upper")

    candidates = plugin.discover_cover_candidates(source_dir)

    assert [item["candidate_id"] for item in candidates] == [
        "file:cover.jpeg",
        "file:cover.jpeg#2",
    ]
    assert [item["cache_key"] for item in candidates] == [
        "file:cover.jpeg",
        "file:cover.jpeg#2",
    ]
    assert {Path(item["path"]).name for item in candidates} == {"COVER.JPEG", "cover.jpeg"}


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


def test_build_url_candidate_prefers_group_root_and_resolves_mime_and_cache() -> None:
    plugin = CoverHandlerPlugin()

    candidate = plugin.build_url_candidate(
        "https://example.test/cover",
        mime_type="image/webp; charset=binary",
        cache_key="book-123",
        group_root="group",
        stage_root="stage",
    )

    assert candidate == {
        "kind": "url",
        "candidate_id": candidate["candidate_id"],
        "apply_mode": "download",
        "url": "https://example.test/cover",
        "mime_type": "image/webp",
        "cache_key": "book-123",
        "root_name": "group",
    }
    assert candidate["candidate_id"].startswith("url:")


def test_download_output_path_uses_cache_key_and_mime_extension(tmp_path: Path) -> None:
    plugin = CoverHandlerPlugin()

    output = plugin._download_output_path(
        tmp_path,
        url="https://example.test/no-extension",
        mime_type="image/png",
        cache_key="cache-book-1",
    )

    assert output.parent == tmp_path
    assert output.suffix == ".png"
    assert output.name.startswith("cover_cache_")


def _file_io_plugin(tmp_path: Path) -> FileIOPlugin:
    roots = {}
    for name in ("inbox", "stage", "outbox", "jobs", "config", "wizards"):
        root = tmp_path / name
        root.mkdir(parents=True, exist_ok=True)
        roots[f"{name}_dir"] = str(root)
    return FileIOPlugin(config={"roots": roots})


def test_discover_cover_candidates_for_ref_returns_resolver_friendly_payload(
    tmp_path: Path,
) -> None:
    plugin = CoverHandlerPlugin()
    file_io = _file_io_plugin(tmp_path)
    source_dir = tmp_path / "inbox" / "Author" / "Book"
    source_dir.mkdir(parents=True)
    (source_dir / "cover.jpeg").write_bytes(b"cover")
    audio_file = source_dir / "book.mp3"
    _write_mp3(audio_file, with_artwork=True)

    candidates = plugin.discover_cover_candidates_for_ref(
        file_service=file_io.file_service,
        source_root="inbox",
        source_relative_path="Author/Book",
        group_root="group",
    )

    assert candidates == [
        {
            "source_root": "inbox",
            "source_relative_path": "Author/Book",
            "root_name": "group",
            "kind": "file",
            "candidate_id": "file:cover.jpeg",
            "apply_mode": "copy",
            "mime_type": "image/jpeg",
            "cache_key": "file:cover.jpeg",
            "candidate_relative_path": "Author/Book/cover.jpeg",
        },
        {
            "source_root": "inbox",
            "source_relative_path": "Author/Book",
            "root_name": "group",
            "kind": "embedded",
            "candidate_id": "embedded:book.mp3",
            "apply_mode": "extract_embedded",
            "mime_type": "image/jpeg",
            "cache_key": "embedded:book.mp3",
            "audio_relative_path": "Author/Book/book.mp3",
        },
    ]


def test_apply_cover_candidate_for_ref_copies_file_to_output_root(
    tmp_path: Path,
) -> None:
    plugin = CoverHandlerPlugin()
    file_io = _file_io_plugin(tmp_path)
    source_dir = tmp_path / "inbox" / "Author" / "Book"
    source_dir.mkdir(parents=True)
    (source_dir / "cover.png").write_bytes(b"cover-bytes")

    result = asyncio.run(
        plugin.apply_cover_candidate_for_ref(
            file_service=file_io.file_service,
            candidate={
                "source_root": "inbox",
                "source_relative_path": "Author/Book",
                "kind": "file",
                "candidate_id": "file:cover.png",
                "apply_mode": "copy",
                "mime_type": "image/png",
                "cache_key": "file:cover.png",
                "candidate_relative_path": "Author/Book/cover.png",
            },
            output_root="stage",
            output_relative_dir="import_runtime/work/Author/Book",
        )
    )

    assert result == {
        "root": "stage",
        "relative_path": "import_runtime/work/Author/Book/cover.png",
    }
    copied = tmp_path / "stage" / "import_runtime" / "work" / "Author" / "Book" / "cover.png"
    assert copied.read_bytes() == b"cover-bytes"
