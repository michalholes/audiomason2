from __future__ import annotations

from plugins.file_io.service.types import RootName
from plugins.import_cli.plugin import parse_import_cli_args


def test_parse_import_cli_args_defaults() -> None:
    args = parse_import_cli_args([])
    assert args.root == RootName.INBOX
    assert args.path == "."
    assert args.mode == "stage"
    assert args.parallelism_n == 1
    assert args.all_books is False
    assert args.book_rel_path is None
    assert args.non_interactive is False
    assert args.yes is False


def test_parse_import_cli_args_flags() -> None:
    args = parse_import_cli_args(
        [
            "--root",
            "stage",
            "--path",
            "authors",
            "--mode",
            "inplace",
            "--parallelism",
            "3",
            "--all",
            "--non-interactive",
            "--yes",
            "--wipe-id3",
            "--cleanup-stage",
            "--archive",
            "--delete-source",
            "--public-db",
            "--run-id",
            "run_abc123",
        ]
    )

    assert args.root == RootName.STAGE
    assert args.path == "authors"
    assert args.mode == "inplace"
    assert args.parallelism_n == 3
    assert args.all_books is True
    assert args.non_interactive is True
    assert args.yes is True
    assert args.wipe_id3 is True
    assert args.cleanup_stage is True
    assert args.archive is True
    assert args.delete_source is True
    assert args.public_db is True
    assert args.run_id == "run_abc123"
