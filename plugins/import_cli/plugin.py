"""CLI import command plugin.

Provides:
  audiomason import

The command is implemented as a plugin-provided CLI command (ICLICommands)
and orchestrates the Import wizard foundation:
- PHASE 0 via plugins.import.preflight
- PHASE 1 via CLI prompts (or non-interactive flags)
- PHASE 2 via persisted Jobs created by plugins.import.services.engine_service

All filesystem operations go through FileService.

ASCII-only.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
from dataclasses import dataclass
from typing import Any

from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

from audiomason.core.config import ConfigResolver
from audiomason.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class ImportCLIArgs:
    root: RootName
    path: str
    mode: str
    parallelism_n: int
    all_books: bool
    book_rel_path: str | None
    non_interactive: bool
    yes: bool
    no_color: bool
    run_id: str | None

    wipe_id3: bool | None
    cleanup_stage: bool
    archive: bool
    delete_source: bool
    public_db: bool


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="audiomason import", add_help=False)

    p.add_argument("--help", "-h", action="store_true")

    p.add_argument("--root", default=RootName.INBOX.value)
    p.add_argument("--path", default=".")
    p.add_argument("--mode", default="stage", choices=["stage", "inplace", "hybrid"])
    p.add_argument("--parallelism", type=int, default=1)

    p.add_argument("--all", dest="all_books", action="store_true")
    p.add_argument("--book-rel-path", default=None)

    p.add_argument("--non-interactive", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--no-color", action="store_true")

    p.add_argument("--run-id", default=None)

    p.add_argument("--wipe-id3", dest="wipe_id3", action="store_true")
    p.add_argument("--no-wipe-id3", dest="wipe_id3", action="store_false")
    p.set_defaults(wipe_id3=None)

    p.add_argument("--cleanup-stage", action="store_true")
    p.add_argument("--archive", action="store_true")
    p.add_argument("--delete-source", action="store_true")
    p.add_argument("--public-db", action="store_true")

    return p


def parse_import_cli_args(argv: list[str]) -> ImportCLIArgs:
    """Parse argv for unit tests and the command implementation."""
    ns = _build_parser().parse_args(argv)

    try:
        root = RootName(str(ns.root))
    except Exception:
        root = RootName.INBOX

    parallelism_n = int(ns.parallelism) if int(ns.parallelism) > 0 else 1

    return ImportCLIArgs(
        root=root,
        path=str(ns.path or "."),
        mode=str(ns.mode or "stage").strip().lower(),
        parallelism_n=parallelism_n,
        all_books=bool(ns.all_books),
        book_rel_path=str(ns.book_rel_path) if ns.book_rel_path else None,
        non_interactive=bool(ns.non_interactive),
        yes=bool(ns.yes),
        no_color=bool(ns.no_color),
        run_id=str(ns.run_id) if ns.run_id else None,
        wipe_id3=ns.wipe_id3,
        cleanup_stage=bool(ns.cleanup_stage),
        archive=bool(ns.archive),
        delete_source=bool(ns.delete_source),
        public_db=bool(ns.public_db),
    )


def _run_id_for(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\n")
    return "run_" + h.hexdigest()[:12]


def _mods() -> dict[str, Any]:
    # The plugin package is named 'import' which collides with Python syntax,
    # therefore we must use importlib.
    return {
        "PreflightService": importlib.import_module(
            "plugins.import.preflight.service"
        ).PreflightService,
        "ImportEngineService": importlib.import_module(
            "plugins.import.services.engine_service"
        ).ImportEngineService,
        "ImportJobRequest": importlib.import_module("plugins.import.engine.types").ImportJobRequest,
        "ImportRunState": importlib.import_module(
            "plugins.import.session_store.types"
        ).ImportRunState,
        "PreflightResult": importlib.import_module(
            "plugins.import.preflight.types"
        ).PreflightResult,
    }


def _print_help() -> None:
    lines = [
        "Usage:",
        "  audiomason import [--root ROOT] [--path REL] [--mode MODE] [--parallelism N]",
        "",
        "Selection:",
        "  --all                      Import all detected books under the source root",
        "  --book-rel-path REL         Import a single book relative path (non-interactive)",
        "",
        "Modes:",
        "  --non-interactive           No prompts; requires --all or --book-rel-path",
        "  --yes                       Auto-confirm non-interactive actions",
        "",
        "Options:",
        "  --wipe-id3 / --no-wipe-id3  Override wipe-id3 policy",
        "  --cleanup-stage             Cleanup stage after processing",
        "  --archive                   Archive source after processing",
        "  --delete-source             Delete source after processing",
        "  --public-db                 Enable public DB lookup",
        "  --no-color                  Disable ANSI styling",
        "",
        "Resume:",
        "  --run-id RUN_ID             Resume a previous run (run pending jobs)",
    ]
    print("\n".join(lines))


def _prompt_select(prompt: str, options: list[str]) -> str | None:
    if not options:
        return None
    print(prompt)
    for i, opt in enumerate(options, start=1):
        print(f"  [{i}] {opt}")
    while True:
        raw = input("> ").strip()
        if raw.lower() in {"q", "quit", "exit"}:
            return None
        try:
            idx = int(raw)
        except Exception:
            print("Enter a number or 'q' to quit")
            continue
        if 1 <= idx <= len(options):
            return options[idx - 1]
        print("Invalid choice")


def _global_options_from_flags(args: ImportCLIArgs) -> dict[str, Any]:
    opts: dict[str, Any] = {}
    if args.wipe_id3 is not None:
        opts["wipe_id3"] = bool(args.wipe_id3)
    if args.cleanup_stage:
        opts["cleanup_stage"] = True
    if args.archive:
        opts["archive"] = True
    if args.delete_source:
        opts["delete_source"] = True
    if args.public_db:
        opts["public_db"] = True
    return opts


class ImportCLIPlugin:
    def get_cli_commands(self):
        return {"import": self.import_cmd}

    def import_cmd(self, argv: list[str]) -> None:
        args = parse_import_cli_args(argv)
        if "--help" in argv or "-h" in argv:
            _print_help()
            return

        resolver = ConfigResolver()
        fs = FileService.from_resolver(resolver)
        mods = _mods()
        engine = mods["ImportEngineService"](fs=fs)

        # Resume path: run pending jobs for an existing run.
        if args.run_id:
            ran = engine.run_pending(limit=args.parallelism_n)
            print(f"Ran {len(ran)} job(s) for run_id={args.run_id}")
            for jid in ran:
                print(f"  {jid}")
            return

        preflight_svc = mods["PreflightService"](fs)
        preflight = preflight_svc.run(args.root, args.path)

        if not preflight.books:
            print("No books detected under the selected source root.")
            return

        selected_books = []
        if args.all_books:
            selected_books = list(preflight.books)
        elif args.non_interactive:
            if args.book_rel_path is None:
                print("Non-interactive mode requires --all or --book-rel-path")
                _print_help()
                return
            selected = [b for b in preflight.books if b.rel_path == args.book_rel_path]
            if not selected:
                print("book_rel_path not found in preflight")
                return
            selected_books = selected
        else:
            author = _prompt_select("Select author (or q to quit):", list(preflight.authors))
            if author is None:
                return
            books = [b for b in preflight.books if b.author == author]
            book_names = [b.rel_path for b in books]
            book_rel = _prompt_select("Select book (or q to quit):", book_names)
            if book_rel is None:
                return
            selected_books = [b for b in books if b.rel_path == book_rel]

        # Build run state.
        selected_rel_paths = sorted([b.rel_path for b in selected_books])
        run_id = _run_id_for(
            str(args.root.value), args.path, ",".join(selected_rel_paths), args.mode
        )

        state = mods["ImportRunState"](
            source_selection_snapshot={
                "root": str(args.root.value),
                "source_root_rel_path": args.path,
                "selected_book_rel_paths": selected_rel_paths,
            },
            source_handling_mode=args.mode,
            parallelism_n=int(args.parallelism_n),
            global_options=_global_options_from_flags(args),
        )

        preflight_subset = mods["PreflightResult"](
            source_root_rel_path=preflight.source_root_rel_path,
            authors=sorted({b.author for b in selected_books}),
            books=selected_books,
        )

        decisions = engine.resolve_book_decisions(preflight=preflight_subset, state=state)
        job_ids = engine.start_import_job(
            mods["ImportJobRequest"](
                run_id=run_id,
                source_root=str(args.root.value),
                state=state,
                decisions=decisions,
            )
        )

        print(f"Created import run: {run_id}")
        print(f"Jobs: {len(job_ids)}")
        for jid in job_ids:
            print(f"  {jid}")

        # Minimal background execution indicator: run up to parallelism jobs once.
        ran = engine.run_pending(limit=args.parallelism_n)
        if ran:
            print(f"Executed {len(ran)} job(s) in background.")
