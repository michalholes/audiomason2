from __future__ import annotations


def test_config_edit_roundtrip_preserves_comments_and_builds_policy():
    from pathlib import Path

    from am_patch.config_edit import apply_update_to_config_text
    from am_patch.config_schema import get_policy_schema

    cfg_path = Path(__file__).parent.parent / "scripts" / "am_patch" / "am_patch.toml"
    original = cfg_path.read_text(encoding="utf-8")
    schema = get_policy_schema()

    updated = apply_update_to_config_text(
        original,
        {
            "ipc_socket_enabled": False,
            "verbosity": "quiet",
            "success_archive_name": "{repo}-{branch}.zip",
        },
        schema,
    )

    # Inline comment on verbosity line must remain.
    assert "# debug | verbose | normal | quiet" in updated

    # Updated values must be present.
    assert 'verbosity = "quiet"' in updated
    assert "ipc_socket_enabled = false" in updated
    assert 'success_archive_name = "{repo}-{branch}.zip"' in updated
