from __future__ import annotations

from importlib import import_module

build_job_requests = import_module("plugins.import.job_requests").build_job_requests


def test_build_job_requests_adds_explicit_phase2_capabilities() -> None:
    doc = build_job_requests(
        session_id="s1",
        root="inbox",
        relative_path="Author/Book",
        mode="stage",
        diagnostics_context={"model_fingerprint": "m1"},
        config_fingerprint="cfg1",
        plan={
            "selected_books": [
                {
                    "book_id": "book:1",
                    "source_relative_path": "Author/Book",
                    "proposed_target_relative_path": "Author/Book",
                }
            ],
            "summary": {"selected_books": 1},
        },
        inputs={
            "covers_policy": {"mode": "embedded"},
            "conflict_policy": {"mode": "overwrite"},
            "delete_source_policy": {"enabled": True},
        },
        session_authority={
            "book_meta": {
                "book:1": {
                    "author_label": "Canonical Author",
                    "book_label": "Canonical Book",
                }
            },
            "phase2_inputs": {
                "publish_policy": {"target_root": "outbox"},
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
    assert capabilities[3]["root"] == "outbox"
    assert capabilities[3]["overwrite"] is True
    assert doc["plan_fingerprint"]
