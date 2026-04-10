"""Issue 138: cover_handler ref-based candidate surfaces."""

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


def _file_io_plugin(tmp_path: Path) -> FileIOPlugin:
    roots = {}
    for name in ("inbox", "stage", "outbox", "jobs", "config", "wizards"):
        root = tmp_path / name
        root.mkdir(parents=True, exist_ok=True)
        roots[f"{name}_dir"] = str(root)
    return FileIOPlugin(config={"roots": roots})


def _candidate_names(candidates: list[dict[str, str]]) -> list[str]:
    names: list[str] = []
    for candidate in candidates:
        rel_path = str(candidate.get("candidate_relative_path") or "")
        audio_rel = str(candidate.get("audio_relative_path") or "")
        leaf = Path(rel_path or audio_rel).name
        names.append(leaf)
    return names


def test_discover_cover_candidates_for_ref_primary_only_ordering(tmp_path: Path) -> None:
    plugin = CoverHandlerPlugin()
    file_io = _file_io_plugin(tmp_path)
    source_dir = tmp_path / "inbox" / "book"
    source_dir.mkdir(parents=True)
    for name in ["folder.png", "cover.jpeg", "zzz.jpg", "aaa.webp"]:
        (source_dir / name).write_bytes(name.encode("utf-8"))

    candidates = plugin.discover_cover_candidates_for_ref(
        file_service=file_io.file_service,
        source_root="inbox",
        source_relative_path="book",
    )

    assert [
        (item["kind"], name, item["apply_mode"])
        for item, name in zip(candidates, _candidate_names(candidates), strict=True)
    ] == [
        ("file", "cover.jpeg", "copy"),
        ("file", "folder.png", "copy"),
        ("file", "aaa.webp", "copy"),
        ("file", "zzz.jpg", "copy"),
    ]


def test_discover_cover_candidates_for_ref_fallback_only_ordering(tmp_path: Path) -> None:
    plugin = CoverHandlerPlugin()
    file_io = _file_io_plugin(tmp_path)
    source_dir = tmp_path / "inbox" / "Author" / "Book"
    source_dir.mkdir(parents=True)
    parent_dir = source_dir.parent
    for name in ["folder.png", "cover.jpeg", "zzz.jpg", "aaa.webp"]:
        (parent_dir / name).write_bytes(name.encode("utf-8"))

    candidates = plugin.discover_cover_candidates_for_ref(
        file_service=file_io.file_service,
        source_root="inbox",
        source_relative_path="Author/Book",
    )

    assert _candidate_names(candidates) == ["cover.jpeg", "folder.png", "aaa.webp", "zzz.jpg"]


def test_discover_cover_candidates_for_ref_orders_primary_before_fallback(
    tmp_path: Path,
) -> None:
    plugin = CoverHandlerPlugin()
    file_io = _file_io_plugin(tmp_path)
    source_dir = tmp_path / "inbox" / "Author" / "Book"
    source_dir.mkdir(parents=True)
    parent_dir = source_dir.parent
    (source_dir / "folder.png").write_bytes(b"primary")
    (parent_dir / "cover.jpeg").write_bytes(b"fallback-named")
    (parent_dir / "zzz.jpg").write_bytes(b"fallback-generic")

    candidates = plugin.discover_cover_candidates_for_ref(
        file_service=file_io.file_service,
        source_root="inbox",
        source_relative_path="Author/Book",
    )

    assert _candidate_names(candidates) == ["folder.png", "cover.jpeg", "zzz.jpg"]


def test_discover_cover_candidates_for_ref_appends_embedded_after_probe(
    tmp_path: Path,
) -> None:
    plugin = CoverHandlerPlugin()
    file_io = _file_io_plugin(tmp_path)
    source_dir = tmp_path / "inbox" / "book"
    source_dir.mkdir(parents=True)
    (source_dir / "cover.jpeg").write_bytes(b"cover")
    audio_file = source_dir / "book.mp3"
    _write_mp3(audio_file, with_artwork=True)

    candidates = plugin.discover_cover_candidates_for_ref(
        file_service=file_io.file_service,
        source_root="inbox",
        source_relative_path="book",
    )

    discovered = [
        (item["kind"], name)
        for item, name in zip(candidates, _candidate_names(candidates), strict=True)
    ]
    assert discovered == [("file", "cover.jpeg"), ("embedded", "book.mp3")]
    assert candidates[-1]["cache_key"] == "embedded:book.mp3"


def test_discover_cover_candidates_for_ref_skips_embedded_without_artwork(
    tmp_path: Path,
) -> None:
    plugin = CoverHandlerPlugin()
    file_io = _file_io_plugin(tmp_path)
    source_dir = tmp_path / "inbox" / "book"
    source_dir.mkdir(parents=True)
    audio_file = source_dir / "book.mp3"
    _write_mp3(audio_file, with_artwork=False)

    candidates = plugin.discover_cover_candidates_for_ref(
        file_service=file_io.file_service,
        source_root="inbox",
        source_relative_path="book",
    )

    assert candidates == []


def test_discover_cover_candidates_for_ref_disambiguates_duplicate_basenames(
    tmp_path: Path,
) -> None:
    plugin = CoverHandlerPlugin()
    file_io = _file_io_plugin(tmp_path)
    source_dir = tmp_path / "inbox" / "Author" / "Book"
    source_dir.mkdir(parents=True)
    parent_dir = source_dir.parent
    (source_dir / "cover.jpeg").write_bytes(b"primary")
    (parent_dir / "cover.jpeg").write_bytes(b"fallback")

    candidates = plugin.discover_cover_candidates_for_ref(
        file_service=file_io.file_service,
        source_root="inbox",
        source_relative_path="Author/Book",
    )

    assert [item["candidate_id"] for item in candidates] == [
        "file:cover.jpeg",
        "file:cover.jpeg@fallback",
    ]
    assert [item["cache_key"] for item in candidates] == [
        "file:cover.jpeg",
        "file:cover.jpeg@fallback",
    ]


def test_discover_cover_candidates_for_ref_disambiguates_case_variants(
    tmp_path: Path,
) -> None:
    plugin = CoverHandlerPlugin()
    file_io = _file_io_plugin(tmp_path)
    source_dir = tmp_path / "inbox" / "book"
    source_dir.mkdir(parents=True)
    (source_dir / "cover.jpeg").write_bytes(b"lower")
    (source_dir / "COVER.JPEG").write_bytes(b"upper")

    candidates = plugin.discover_cover_candidates_for_ref(
        file_service=file_io.file_service,
        source_root="inbox",
        source_relative_path="book",
    )

    assert [item["candidate_id"] for item in candidates] == [
        "file:cover.jpeg",
        "file:cover.jpeg#2",
    ]
    assert [item["cache_key"] for item in candidates] == [
        "file:cover.jpeg",
        "file:cover.jpeg#2",
    ]
    assert set(_candidate_names(candidates)) == {"COVER.JPEG", "cover.jpeg"}


def test_build_embedded_extract_commands_for_m4a_has_fallback(tmp_path: Path) -> None:
    plugin = CoverHandlerPlugin()
    audio_file = tmp_path / "book.m4a"
    output = tmp_path / "cover.jpg"

    commands = plugin.build_embedded_extract_commands(audio_file, output)

    assert len(commands) == 2
    assert commands[0][-3:] == ["-c:v", "copy", str(output)]
    assert commands[1][-5:] == ["-map", "0:v:0", "-frames:v", "1", str(output)]


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


def test_apply_cover_candidate_for_ref_copies_file_to_output_root(tmp_path: Path) -> None:
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


def test_cover_boundary_resolves_plugin_via_shared_import_seam(monkeypatch, tmp_path: Path) -> None:
    boundary = __import__("plugins.import.cover_boundary", fromlist=["discover_cover_candidates"])
    file_io = _file_io_plugin(tmp_path)
    source_dir = tmp_path / "inbox" / "book"
    source_dir.mkdir(parents=True)
    (source_dir / "cover.jpeg").write_bytes(b"cover")

    plugin = CoverHandlerPlugin()
    seen: dict[str, str] = {}

    def _resolve_import_plugin(*, plugin_name: str):
        seen["plugin_name"] = plugin_name
        return plugin

    monkeypatch.setattr(boundary, "resolve_import_plugin", _resolve_import_plugin)

    candidates = boundary.discover_cover_candidates(
        fs=file_io.file_service,
        source_root="inbox",
        source_prefix="",
        source_relative_path="book",
    )

    assert seen == {"plugin_name": "cover_handler"}
    assert [item["candidate_id"] for item in candidates] == ["file:cover.jpeg"]


def test_cover_boundary_source_has_no_local_loader_or_root_resolver() -> None:
    source = Path("plugins/import/cover_boundary.py").read_text(encoding="utf-8")

    assert "PluginLoader" not in source
    assert "PluginRegistry" not in source
    assert "ConfigService" not in source
    assert "_builtin_plugins_root" not in source
    assert "_user_plugins_root" not in source
    assert 'resolve_import_plugin(plugin_name="cover_handler")' in source
