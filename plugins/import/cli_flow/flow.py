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


def _ui_select(ui, prompt: str, options: list[str], *, default_index: int = 1) -> str | None:
    """Call ui.select with optional default_index, preserving backward compatibility."""

    try:
        return ui.select(prompt, options, default_index=default_index)
    except TypeError:
        return ui.select(prompt, options)


@dataclass(frozen=True)
class ImportCliArgs:
    root: RootName
    source_root_rel_path: str
    mode: Literal["stage", "inplace"]
    mode_provided: bool


def _parse_import_cli_args(argv: list[str]) -> ImportCliArgs:
    """Parse import plugin args (deterministic; no argparse dependency)."""

    root = RootName.INBOX
    source_root_rel_path = "."
    mode: Literal["stage", "inplace"] = "stage"
    mode_provided = False

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
                mode_provided = True
        elif arg in {"--help", "-h"}:
            raise ValueError("help")

        i += 1

    return ImportCliArgs(
        root=root,
        source_root_rel_path=source_root_rel_path,
        mode=mode,
        mode_provided=mode_provided,
    )


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
    # PHASE 1: Step 1 - Work mode selection
    # ===========================================
    selected_mode: Literal["stage", "inplace"] = args.mode
    if args.mode_provided:
        ui.print(f"Mode: {selected_mode}")
    else:
        m = _ui_select(ui, "Select work mode:", ["stage", "inplace"], default_index=1)
        if m is None:
            return 0
        selected_mode = cast(Literal["stage", "inplace"], str(m))

    # ===========================================
    # PHASE 1: Step 2 - Lookup toggle
    # ===========================================
    lookup_enabled = ui.confirm("Enable lookup (public DB)?", default=True)
    # Use a dedicated PreflightService instance so lookup is consistently reflected
    # in plan/preview (Phase 1), without changing Phase 0 fast-index behavior.
    try:
        preflight_plan = PreflightService(fs, enable_lookup=bool(lookup_enabled))
    except TypeError:
        # Backward compatibility: some tests stub PreflightService without this kwarg.
        preflight_plan = PreflightService(fs)

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
        sel = _ui_select(ui, "Select author:", authors)
        if sel is None:
            return 0
        selected_author = "" if sel == book_only_label else sel

    books_for_author = [b for b in idx.books if b.author == selected_author]
    if not books_for_author:
        ui.print("No books detected for the selected author.")
        return 0

    book_options = [b.rel_path for b in books_for_author]
    rel = _ui_select(ui, "Select book:", book_options)
    if rel is None:
        return 0

    selected = [b for b in books_for_author if b.rel_path == rel]
    if not selected:
        ui.print("No book selected.")
        return 0
    book = selected[0]

    plan = preflight_plan.plan_preview_for_book(
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

    if not lookup_enabled:
        lookup_line = "skipped"
    elif plan.lookup.status == "error":
        lookup_line = "failed"
    else:
        lookup_line = "succeeded"

    ui.print(f"  Lookup:          {lookup_line}")
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

    # Step 3 - Filename policy
    # Keep legacy prompt for backward-compat tests (Issue 600), but always collect
    # the full filename policy required by Issue 603.
    _legacy_filename_norm_enabled = ui.confirm("Enable filename normalization?", default=True)

    norm_strategy = _ui_select(
        ui,
        "Filename normalization strategy:",
        ["numeric_only", "numeric_suffix", "keep_original"],
        default_index=1,
    )
    if norm_strategy is None:
        return 0

    padding = _ui_select(
        ui,
        "Filename padding:",
        ["auto", "fixed_2", "fixed_3", "fixed_4"],
        default_index=1,
    )
    if padding is None:
        return 0

    strictness = _ui_select(
        ui,
        "Filename strictness:",
        ["warn_best_effort", "strict_fail", "silent_best_effort"],
        default_index=1,
    )
    if strictness is None:
        return 0

    char_policy = _ui_select(
        ui,
        "Output filename character policy:",
        ["allow_unicode", "ascii_only"],
        default_index=1,
    )
    if char_policy is None:
        return 0

    filename_normalization = {
        "strategy": str(norm_strategy),
        "padding": str(padding),
        "strictness": str(strictness),
        "char_policy": str(char_policy),
        "legacy_enabled": bool(_legacy_filename_norm_enabled),
    }

    # Step 4 - Covers handling
    covers_policy = _ui_select(
        ui,
        "Covers policy:",
        [
            "keep_existing",
            "prefer_embedded",
            "prefer_external",
            "remove_covers",
        ],
        default_index=1,
    )
    if covers_policy is None:
        return 0
    confirmed_remove = False
    if str(covers_policy) == "remove_covers":
        confirmed_remove = ui.confirm("This will remove covers during processing", default=False)
    covers = {"policy": str(covers_policy), "confirmed_remove": bool(confirmed_remove)}

    # Step 5 - ID3 handling
    wipe_id3 = ui.confirm("Wipe ID3 tags before writing new metadata?", default=False)
    confirmed_wipe = False
    if wipe_id3:
        confirmed_wipe = ui.confirm("This is destructive", default=False)
    id3 = {"wipe": bool(wipe_id3), "confirmed_wipe": bool(confirmed_wipe)}

    # Step 6 - Audio processing (branching fix)
    audio_processing_enabled = ui.confirm("Enable audio processing?", default=False)

    audio_processing_profile = None
    if audio_processing_enabled:
        # Legacy prompt required by Issue 600 tests.
        audio_processing_profile = _ui_select(
            ui,
            "Select audio processing profile:",
            [
                "default",
                "passthrough",
            ],
            default_index=1,
        )
        if audio_processing_profile is None:
            return 0

    loudnorm = False
    bitrate_change_enabled = False
    bitrate_kbps: int | None = None
    bitrate_mode: str | None = None
    confirmed_audio = False

    if audio_processing_enabled:
        loudnorm = ui.confirm("Enable loudnorm?", default=False)
        bitrate_change_enabled = ui.confirm("Enable bitrate change?", default=False)
        if bitrate_change_enabled:
            br_raw = ui.prompt_text("Bitrate kbps", "96")
            try:
                n = int(str(br_raw).strip())
                if n >= 8:
                    bitrate_kbps = n
            except Exception:
                bitrate_kbps = None

            bm = _ui_select(ui, "Bitrate mode:", ["cbr", "vbr"], default_index=1)
            if bm is None:
                return 0
            bitrate_mode = str(bm)

        confirmed_audio = ui.confirm("Confirm audio processing configuration?", default=False)

    audio_processing = {
        "enabled": bool(audio_processing_enabled),
        "confirmed": bool(confirmed_audio),
        "loudnorm": bool(loudnorm),
        "bitrate_change_enabled": bool(bitrate_change_enabled),
        "bitrate_kbps": bitrate_kbps,
        "bitrate_mode": bitrate_mode,
    }
    if audio_processing_profile is not None:
        audio_processing["profile"] = str(audio_processing_profile)

    # Step 7 - Publish
    publish_enabled = ui.confirm("Publish book after processing?", default=False)
    publish = {"enabled": bool(publish_enabled)}

    # Step 8 - Delete source
    delete_source = ui.confirm("Delete source after import?", default=False)
    delete_policy: dict[str, object] = {"enabled": bool(delete_source), "guard_enabled": True}
    if delete_source:
        guard_enabled = ui.confirm("Enable delete guard?", default=True)
        delete_policy["guard_enabled"] = bool(guard_enabled)

    # Step 9 - Conflict policy
    conflict_policy = _ui_select(
        ui,
        "Select conflict policy:",
        [
            "overwrite",
            "skip",
            "version_suffix",
        ],
        default_index=1,
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

    ui.print("\nFinal summary:")
    ui.print(f"  Mode: {selected_mode}")
    ui.print(f"  Lookup enabled: {int(bool(lookup_enabled))}")
    ui.print(f"  Filename normalization: {filename_normalization}")
    ui.print(f"  Covers: {covers}")
    ui.print(f"  ID3: {id3}")
    ui.print(f"  Audio processing: {audio_processing}")
    ui.print(f"  Publish: {publish}")
    ui.print(f"  Delete source: {delete_policy}")
    ui.print(f"  Conflict policy: {conflict_policy}")
    ui.print(f"  Parallelism override: {par_override}")

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
        source_handling_mode=selected_mode,
        parallelism_n=2 if selected_mode == "stage" else 1,
        global_options={
            "mode": selected_mode,
            "lookup_enabled": bool(lookup_enabled),
            "effective_author": eff_author,
            "effective_title": eff_title,
            "rename_preview": dict(plan.rename_preview),
            "filename_normalization": filename_normalization,
            "covers": covers,
            "id3": id3,
            "audio_processing": audio_processing,
            "publish": publish,
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
        handling_mode=selected_mode,
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
