from __future__ import annotations

from importlib import import_module

build_job_requests = import_module("plugins.import.job_requests").build_job_requests


def test_build_job_requests_uses_phase1_authority_without_path_fallback() -> None:
    doc = build_job_requests(
        session_id="s1",
        root="inbox",
        relative_path="Raw/Source",
        mode="stage",
        diagnostics_context={"model_fingerprint": "m1"},
        config_fingerprint="cfg1",
        plan={
            "selected_books": [
                {
                    "book_id": "book:1",
                    "source_relative_path": "Shelf/Disc-01",
                    "proposed_target_relative_path": "Stage/Disc-01",
                }
            ],
            "summary": {"selected_books": 1},
        },
        inputs={
            "covers_policy": {"mode": "skip"},
            "conflict_policy": {"mode": "ask"},
            "delete_source_policy": {"enabled": False},
            "id3_policy": {"values": {"title": "Path Derived"}},
        },
        session_authority={
            "book_meta": {
                "book:1": {
                    "author_label": "Canonical Author",
                    "book_label": "Canonical Book",
                    "display_label": "Canonical Author / Canonical Book",
                }
            },
            "phase2_inputs": {
                "covers_policy": {"mode": "embedded"},
                "conflict_policy": {"mode": "overwrite"},
                "delete_source_policy": {"enabled": True},
                "publish_policy": {"target_root": "outbox"},
            },
            "runtime": {
                "effective_author_title": {
                    "author": "Canonical Author",
                    "title": "Canonical Book",
                }
            },
        },
    )

    action = doc["actions"][0]
    capabilities = action["capabilities"]

    assert [cap["kind"] for cap in capabilities] == [
        "audio.import",
        "cover.embed",
        "metadata.tags",
        "publish.write",
        "source.delete",
    ]
    assert [cap["order"] for cap in capabilities] == [10, 20, 30, 40, 50]
    assert capabilities[2]["field_map"] == {
        "title": "book_title",
        "artist": "author",
        "album": "book_title",
        "album_artist": "author",
    }
    assert capabilities[2]["values"] == {
        "title": "Canonical Book",
        "artist": "Canonical Author",
        "album": "Canonical Book",
        "album_artist": "Canonical Author",
    }
    assert "Shelf" not in capabilities[2]["values"].values()
    assert "Disc-01" not in capabilities[2]["values"].values()
    assert capabilities[3]["root"] == "outbox"
    assert capabilities[3]["overwrite"] is True
    assert action["authority"] == {
        "book": {
            "author_label": "Canonical Author",
            "book_label": "Canonical Book",
            "display_label": "Canonical Author / Canonical Book",
        },
        "metadata_tags": {
            "field_map": {
                "title": "book_title",
                "artist": "author",
                "album": "book_title",
                "album_artist": "author",
            },
            "values": {
                "title": "Canonical Book",
                "artist": "Canonical Author",
                "album": "Canonical Book",
                "album_artist": "Canonical Author",
            },
        },
        "publish": {"root": "outbox", "relative_path": "Stage/Disc-01"},
    }
    assert doc["authority"]["phase1"]["selected_books"]["book:1"]["book_label"] == "Canonical Book"
    assert doc["authority"]["phase1"]["runtime"]["effective_author_title"] == {
        "author": "Canonical Author",
        "title": "Canonical Book",
    }
    assert doc["plan_fingerprint"]


def test_build_job_requests_requires_selected_books_for_planned_units() -> None:
    doc = build_job_requests(
        session_id="s1",
        root="inbox",
        relative_path="Raw/Source",
        mode="stage",
        diagnostics_context={},
        config_fingerprint="cfg1",
        plan={"source": {"relative_path": "Raw/Source"}},
        inputs={},
        session_authority={"phase2_inputs": {}},
    )

    assert doc["actions"] == []
