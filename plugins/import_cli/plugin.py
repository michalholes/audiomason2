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
import json
import sys
from dataclasses import dataclass
from typing import Any

from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

from audiomason.core.config import ConfigResolver
from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus
from audiomason.core.logging import get_logger

log = get_logger(__name__)


def _emit_diag(event: str, *, operation: str, data: dict[str, Any]) -> None:
    try:
        env = build_envelope(
            event=event,
            component="import_cli",
            operation=operation,
            data=data,
        )
        get_event_bus().publish(event, env)
    except Exception:
        return


def _cli_overrides_from_sys_argv(argv: list[str]) -> dict[str, Any]:
    """Extract minimal ConfigResolver CLI overrides from the process argv.

    The import CLI command is invoked through the top-level CLI plugin, which
    parses and removes verbosity flags before dispatching to plugin commands.
    This helper re-reads sys.argv to obtain the effective global overrides.

    Only a minimal subset is extracted to avoid duplicating CLI parsing logic.
    """

    cli_args: dict[str, Any] = {}

    def _ensure_dict(root: dict[str, Any], key: str) -> dict[str, Any]:
        val = root.get(key)
        if isinstance(val, dict):
            return val
        new: dict[str, Any] = {}
        root[key] = new
        return new

    for arg in argv:
        if arg in ("-q", "--quiet"):
            _ensure_dict(cli_args, "logging")["level"] = "quiet"
        elif arg in ("-v", "--verbose"):
            _ensure_dict(cli_args, "logging")["level"] = "verbose"
        elif arg in ("-d", "--debug"):
            _ensure_dict(cli_args, "logging")["level"] = "debug"
        elif arg == "--diagnostics":
            _ensure_dict(cli_args, "diagnostics")["enabled"] = True
        elif arg == "--no-diagnostics":
            _ensure_dict(cli_args, "diagnostics")["enabled"] = False

    return cli_args


def _install_console_diag_subscriber(*, enabled: bool) -> None:
    if not enabled:
        return

    def _on_any_event(event: str, data: dict[str, Any]) -> None:
        if not isinstance(data, dict):
            return
        comp = data.get("component")
        if comp not in ("import_cli", "import.preflight", "import.engine"):
            return
        try:
            line = json.dumps(data, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        except Exception:
            return
        print(f"DIAG {line}")

    get_event_bus().subscribe_all(_on_any_event)


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
        _emit_diag(
            "boundary.start",
            operation="import_cmd",
            data={"argv": list(argv)},
        )
        args = parse_import_cli_args(argv)
        if "--help" in argv or "-h" in argv:
            _print_help()
            _emit_diag(
                "boundary.end",
                operation="import_cmd",
                data={"status": "succeeded", "reason": "help"},
            )
            return

        resolver = ConfigResolver(cli_args=_cli_overrides_from_sys_argv(sys.argv))
        # In debug mode, surface import diagnostics envelopes on stdout.
        try:
            debug_enabled = resolver.resolve_logging_level() == "debug"
        except Exception:
            debug_enabled = False
        _install_console_diag_subscriber(enabled=debug_enabled)

        fs = FileService.from_resolver(resolver)
        mods = _mods()
        engine = mods["ImportEngineService"](fs=fs)

        # Resume path: run pending jobs for an existing run.
        if args.run_id:
            ran = engine.run_pending(limit=args.parallelism_n)
            print(f"Ran {len(ran)} job(s) for run_id={args.run_id}")
            for jid in ran:
                print(f"  {jid}")
            _emit_diag(
                "boundary.end",
                operation="import_cmd",
                data={"status": "succeeded", "reason": "resume", "ran_n": len(ran)},
            )
            return

        preflight_svc = mods["PreflightService"](fs)
        preflight = preflight_svc.run(args.root, args.path)

        if not preflight.books:
            print("No books detected under the selected source root.")
            _emit_diag(
                "boundary.end",
                operation="import_cmd",
                data={"status": "succeeded", "reason": "no_books"},
            )
            return

        selected_books: list[Any] = []
        if args.all_books:
            selected_books = list(preflight.books)
        elif args.non_interactive:
            if args.book_rel_path is None:
                print("Error: non-interactive mode requires --all or --book-rel-path")
                _print_help()
                _emit_diag(
                    "boundary.fail",
                    operation="import_cmd",
                    data={"status": "failed", "reason": "missing_selection"},
                )
                raise SystemExit(2)
            selected = [b for b in preflight.books if b.rel_path == args.book_rel_path]
            if not selected:
                print("Error: book_rel_path not found in preflight")
                _emit_diag(
                    "boundary.fail",
                    operation="import_cmd",
                    data={"status": "failed", "reason": "book_rel_path_not_found"},
                )
                raise SystemExit(2)
            selected_books = selected
        else:
            # Interactive selection must support mixed layouts:
            # - Author/Book layout (authors list)
            # - Single-level book directories (author == "")
            # - File units (author == "")
            has_book_only = any(b.author == "" for b in preflight.books)
            author_options: list[str] = list(preflight.authors)
            book_only_label = "<book-only>"
            if has_book_only:
                author_options = author_options + [book_only_label] if author_options else []

            selected_author: str | None
            if author_options:
                while True:
                    selected_author = _prompt_select(
                        "Select author (or q to quit):", author_options
                    )
                    if selected_author is None:
                        _emit_diag(
                            "boundary.end",
                            operation="import_cmd",
                            data={"status": "succeeded", "reason": "user_quit"},
                        )
                        return
                    author_key = "" if selected_author == book_only_label else selected_author
                    books = [b for b in preflight.books if b.author == author_key]
                    if not books:
                        print("No books detected for the selected author.")
                        continue
                    book_names = [b.rel_path for b in books]
                    book_rel = _prompt_select("Select book (or q to quit):", book_names)
                    if book_rel is None:
                        _emit_diag(
                            "boundary.end",
                            operation="import_cmd",
                            data={"status": "succeeded", "reason": "user_quit"},
                        )
                        return
                    selected_books = [b for b in books if b.rel_path == book_rel]
                    break
            else:
                # No authors detected; select directly from all discovered books.
                book_names = [b.rel_path for b in preflight.books]
                book_rel = _prompt_select("Select book (or q to quit):", book_names)
                if book_rel is None:
                    _emit_diag(
                        "boundary.end",
                        operation="import_cmd",
                        data={"status": "succeeded", "reason": "user_quit"},
                    )
                    return
                selected_books = [b for b in preflight.books if b.rel_path == book_rel]

            if not selected_books:
                print("No book selected.")
                _emit_diag(
                    "boundary.end",
                    operation="import_cmd",
                    data={"status": "succeeded", "reason": "no_selection"},
                )
                return

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
            skipped=[],
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

        _emit_diag(
            "boundary.end",
            operation="import_cmd",
            data={"status": "succeeded", "run_id": run_id, "jobs_n": len(job_ids)},
        )
