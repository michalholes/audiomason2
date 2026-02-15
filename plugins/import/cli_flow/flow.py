"""Import CLI flow (PHASE 0 + PHASE 1 + Job start for PHASE 2).

Rules (Issue 600):
- This module contains business logic and state transitions.
- All console IO is delegated to ConsoleUI.
- PHASE 2 remains non-interactive (Jobs only).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

from audiomason.core import ConfigResolver

from ..preflight.service import PreflightService
from ..services.engine_service import ImportEngineService


@dataclass(frozen=True)
class ImportCliArgs:
    root: RootName
    source_root_rel_path: str
    mode: Literal["stage", "inplace"]


def _parse_import_cli_args(argv: list[str]) -> ImportCliArgs:
    """Parse import plugin args (deterministic; no argparse dependency)."""

    root = RootName.INBOX
    source_root_rel_path = "."
    mode: Literal["stage", "inplace"] = "stage"

    i = 0
    while i < len(argv):
        arg = str(argv[i])
        if arg == "--root" and i + 1 < len(argv):
            i += 1
            try:
                root = RootName(str(argv[i]))
            except Exception:
                root = RootName.INBOX
        elif arg == "--path" and i + 1 < len(argv):
            i += 1
            source_root_rel_path = str(argv[i] or ".")
        elif arg == "--mode" and i + 1 < len(argv):
            i += 1
            m = str(argv[i] or "stage").strip().lower()
            if m in {"stage", "inplace"}:
                mode = cast(Literal["stage", "inplace"], m)
        elif arg in {"--help", "-h"}:
            raise ValueError("help")

        i += 1

    return ImportCliArgs(root=root, source_root_rel_path=source_root_rel_path, mode=mode)


def _cli_args_for_resolver_from_sysargv() -> dict:
    """Extract minimal resolver args from sys.argv."""

    import sys

    cli_args: dict = {}
    args = sys.argv[1:]
    if "--diagnostics" in args:
        cli_args.setdefault("diagnostics", {})["enabled"] = True
    if "--no-diagnostics" in args:
        cli_args.setdefault("diagnostics", {})["enabled"] = False
    return cli_args


async def run_import_cli_flow(argv: list[str], ui) -> int:
    """Execute the import CLI flow."""

    try:
        args = _parse_import_cli_args(argv)
    except ValueError as e:
        if str(e) == "help":
            ui.print("Usage: audiomason import [--root ROOT] [--path PATH] [--mode stage|inplace]")
            return 0
        raise

    resolver = ConfigResolver(cli_args=_cli_args_for_resolver_from_sysargv())
    fs = FileService.from_resolver(resolver)

    preflight = PreflightService(fs)

    # ===========================================
    # PHASE 0: Fast Index only (must be immediate)
    # ===========================================
    idx = preflight.fast_index(args.root, args.source_root_rel_path)
    if not idx.books:
        ui.print("No books detected under the selected source root.")
        return 0

    # ===========================================
    # PHASE 1: Selection + Plan/Preview + Confirm
    # ===========================================

    authors = list(idx.authors)
    has_book_only = any(b.author == "" for b in idx.books)
    book_only_label = "<book-only>"
    if has_book_only and book_only_label not in authors:
        authors = authors + [book_only_label] if authors else [book_only_label]

    selected_author = ""
    if authors:
        sel = ui.select("Select author:", authors)
        if sel is None:
            return 0
        selected_author = "" if sel == book_only_label else sel

    books_for_author = [b for b in idx.books if b.author == selected_author]
    if not books_for_author:
        ui.print("No books detected for the selected author.")
        return 0

    book_options = [b.rel_path for b in books_for_author]
    rel = ui.select("Select book:", book_options)
    if rel is None:
        return 0

    selected = [b for b in books_for_author if b.rel_path == rel]
    if not selected:
        ui.print("No book selected.")
        return 0
    book = selected[0]

    plan = preflight.plan_preview_for_book(
        args.root,
        args.source_root_rel_path,
        book_ref=book.book_ref,
        rel_path=book.rel_path,
        unit_type=book.unit_type,
        author=book.author,
        book=book.book,
    )

    ui.print("\nPlan/Preview:")
    ui.print(f"  Proposed author: {plan.proposed_author}")
    ui.print(f"  Proposed title:  {plan.proposed_title}")
    ui.print(f"  Lookup status:   {plan.lookup.status}")
    if plan.lookup.source:
        ui.print(f"  Lookup source:   {plan.lookup.source}")
    if plan.lookup.error:
        ui.print(f"  Lookup error:    {plan.lookup.error}")

    ui.print("\nRename preview:")
    items = sorted(plan.rename_preview.items(), key=lambda kv: (kv[0], kv[1]))
    if not items:
        ui.print("  (none)")
    else:
        for src, dst in items[:200]:
            ui.print(f"  {src} -> {dst}")
        if len(items) > 200:
            ui.print(f"  ... ({len(items) - 200} more)")

    eff_author = ui.prompt_text("Effective author", plan.proposed_author)
    eff_title = ui.prompt_text("Effective title", plan.proposed_title)

    # ===========================================
    # PHASE 1: Additional required wizard options
    # ===========================================

    # 1) Filename normalization options
    filename_normalization_enabled = ui.confirm(
        "Enable filename normalization?",
        default=True,
    )
    filename_normalization_policy = {
        "enabled": bool(filename_normalization_enabled),
        "strategy": "basic",
    }

    # 2) Audio processing configuration (explicit confirmation)
    audio_processing_enabled = ui.confirm(
        "Enable audio processing?",
        default=True,
    )
    audio_processing_profile = ui.select(
        "Select audio processing profile:",
        [
            "default",
            "passthrough",
        ],
    )
    if audio_processing_profile is None:
        return 0
    audio_processing = {
        "enabled": bool(audio_processing_enabled),
        "profile": str(audio_processing_profile),
    }
    if not ui.confirm("Confirm audio processing configuration?", default=True):
        ui.print("Not started.")
        return 0

    # 3) Delete source + guard toggle
    delete_source = ui.confirm("Delete source after import?", default=False)
    delete_guard_enabled = ui.confirm("Enable delete guard?", default=True)
    delete_policy = {
        "enabled": bool(delete_source),
        "guard_enabled": bool(delete_guard_enabled),
    }

    # 4) Conflict policy
    conflict_policy = ui.select(
        "Select conflict policy:",
        [
            "overwrite",
            "skip",
            "version_suffix",
        ],
    )
    if conflict_policy is None:
        return 0

    # 5) Optional parallelism override (stored only; enforcement unchanged)
    par_raw = ui.prompt_text("Parallelism override (empty = auto)", "")
    par_override: int | None = None
    if str(par_raw or "").strip():
        try:
            n = int(str(par_raw).strip())
            if n >= 1:
                par_override = n
        except Exception:
            par_override = None

    if not ui.confirm("Start processing now?", default=False):
        ui.print("Not started.")
        return 0

    # ===========================================
    # PHASE 2: Start jobs (non-interactive)
    # ===========================================
    engine = ImportEngineService(fs=fs)

    import uuid

    from ..engine.types import BookDecision, ImportJobRequest
    from ..session_store.types import ImportRunState

    run_id = "run_import_" + uuid.uuid4().hex[:12]

    state = ImportRunState(
        source_selection_snapshot={
            "root": str(args.root.value),
            "source_root_rel_path": args.source_root_rel_path,
            "selected_book_rel_paths": [book.rel_path],
        },
        source_handling_mode=args.mode,
        parallelism_n=2 if args.mode == "stage" else 1,
        global_options={
            "effective_author": eff_author,
            "effective_title": eff_title,
            "rename_preview": dict(plan.rename_preview),
            "filename_normalization_policy": filename_normalization_policy,
            "audio_processing": audio_processing,
            "delete_source": delete_policy,
            "conflict_policy": str(conflict_policy),
            "parallelism_override": par_override,
        },
    )

    dec = BookDecision(
        book_rel_path=book.rel_path,
        unit_type=str(book.unit_type or "dir"),
        source_ext=None,
        author=eff_author,
        title=eff_title,
        handling_mode=args.mode,
        rename_preview=dict(plan.rename_preview),
        options=state.global_options,
    )

    req = ImportJobRequest(
        run_id=run_id,
        source_root=str(args.root.value),
        state=state,
        decisions=[dec],
    )

    job_ids = engine.start_import_job(req)
    ran = engine.run_pending(limit=state.parallelism_n)

    ui.print(f"Created {len(job_ids)} job(s) for run_id={run_id}")
    if ran:
        ui.print(f"Ran {len(ran)} job(s)")
    for jid in job_ids:
        ui.print(f"  {jid}")

    return 0
