"""Import Wizard Engine (plugin: import).

Implements PHASE 0 discovery, model load/validate, session lifecycle, and
minimal plan/job request generation.

No UI is implemented here.

ASCII-only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from audiomason.core.config import ConfigResolver
from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus
from plugins.file_io.service import FileService, RootName

from . import discovery as discovery_mod
from .defaults import ensure_default_models
from .errors import (
    FinalizeError,
    ImportWizardError,
    ModelValidationError,
    SessionNotFoundError,
    StepSubmissionError,
    error_envelope,
    invariant_violation,
    validation_error,
)
from .fingerprints import fingerprint_json, sha256_hex
from .flow_runtime import (
    CANONICAL_STEP_ORDER,
    CONDITIONAL_STEP_IDS,
    build_flow_model,
)
from .flow_runtime import (
    OPTIONAL_STEP_IDS as FLOWCFG_OPTIONAL_STEP_IDS,
)
from .job_requests import build_job_requests
from .models import BASE_REQUIRED_STEP_IDS, CatalogModel, FlowModel, validate_models
from .plan import PlanSelectionError, compute_plan
from .serialization import canonical_serialize
from .storage import append_jsonl, atomic_write_json, atomic_write_text, read_json


def _to_ascii(text: str) -> str:
    # Deterministic ASCII-only conversion for UI labels.
    return text.encode("ascii", errors="replace").decode("ascii")


def _derive_selection_items(
    discovery: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Derive stable author/book selectable items from discovery.

    Item ids and ordering must be deterministic (contract 4.3).
    """

    authors: dict[str, dict[str, str]] = {}
    books: dict[str, dict[str, str]] = {}

    dirs: list[str] = []
    for it in discovery:
        if not (isinstance(it, dict) and it.get("kind") == "dir"):
            continue
        rel_any = it.get("relative_path")
        if not isinstance(rel_any, str):
            continue
        rel = rel_any.replace("\\", "/")
        dirs.append(rel)

    # Prefer book directories at depth >= 2 (Author/Book). If absent, fall back to
    # depth >= 1 (single folder sources).
    book_pairs: set[tuple[str, str]] = set()
    for rel in dirs:
        segs = [s for s in rel.split("/") if s]
        if len(segs) >= 2:
            book_pairs.add((segs[0], segs[1]))

    if not book_pairs:
        for rel in dirs:
            segs = [s for s in rel.split("/") if s]
            if len(segs) >= 1:
                book_pairs.add((segs[0], segs[0]))

    if not book_pairs:
        book_pairs.add(("(root)", "(root)"))

    for author_key, book_key in sorted(book_pairs):
        author_label = _to_ascii(author_key)
        book_label = _to_ascii(
            author_key if author_key == book_key else f"{author_key} / {book_key}"
        )

        author_id = "author:" + sha256_hex(f"a|{author_key}".encode())[:16]
        book_id = "book:" + sha256_hex(f"b|{author_key}|{book_key}".encode())[:16]

        if author_id not in authors:
            authors[author_id] = {"item_id": author_id, "label": author_label}
        if book_id not in books:
            books[book_id] = {"item_id": book_id, "label": book_label}

    authors_items = sorted(authors.values(), key=lambda x: (x["label"], x["item_id"]))
    books_items = sorted(books.values(), key=lambda x: (x["label"], x["item_id"]))
    return authors_items, books_items


def _inject_selection_items(
    *,
    effective_model: dict[str, Any],
    authors_items: list[dict[str, str]],
    books_items: list[dict[str, str]],
) -> dict[str, Any]:
    steps_any = effective_model.get("steps")
    if not isinstance(steps_any, list):
        return effective_model

    steps: list[dict[str, Any]] = [s for s in steps_any if isinstance(s, dict)]
    for step in steps:
        step_id = step.get("step_id")
        if step_id not in {"select_authors", "select_books"}:
            continue
        fields_any = step.get("fields")
        if not isinstance(fields_any, list):
            continue
        fields: list[dict[str, Any]] = [f for f in fields_any if isinstance(f, dict)]
        for f in fields:
            if f.get("type") != "multi_select_indexed":
                continue
            if step_id == "select_authors":
                f["items"] = list(authors_items)
            else:
                f["items"] = list(books_items)

    effective_model["steps"] = steps
    return effective_model


def _emit(event: str, operation: str, data: dict[str, Any]) -> None:
    try:
        get_event_bus().publish(
            event,
            build_envelope(
                event=event,
                component="import",
                operation=operation,
                data=data,
            ),
        )
    except Exception:
        # Fail-safe: diagnostics must never crash processing.
        return


def _iso_utc_now() -> str:
    # RFC3339 / ISO-8601 in UTC (Z suffix).
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_session_state_fields(state: dict[str, Any]) -> dict[str, Any]:
    """Ensure SessionState contains minimally required fields (spec 10.*).

    This is a backward-compatible upgrader for existing sessions.
    """
    changed = False

    def _setdefault(key: str, value: Any) -> None:
        nonlocal changed
        if key not in state:
            state[key] = value
            changed = True

    _setdefault("answers", {})
    _setdefault("computed", {})
    _setdefault("selected_author_ids", [])
    _setdefault("selected_book_ids", [])
    _setdefault("effective_author_title", {})

    # Backward compatibility: keep legacy inputs but answers is canonical.
    if "inputs" not in state:
        state["inputs"] = {}
        changed = True

    answers_any = state.get("answers")
    inputs_any = state.get("inputs")

    if (
        isinstance(answers_any, dict)
        and not answers_any
        and isinstance(inputs_any, dict)
        and inputs_any
    ):
        state["answers"] = dict(inputs_any)
        changed = True

    if changed:
        state["updated_at"] = _iso_utc_now()
    return state


def _exception_envelope(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, SessionNotFoundError):
        return error_envelope(
            "NOT_FOUND",
            str(exc) or "not found",
            details=[{"path": "$.session_id", "reason": "not_found", "meta": {}}],
        )
    if isinstance(exc, (StepSubmissionError, ValueError)):
        return validation_error(
            message=str(exc) or "validation error",
            path="$",
            reason="validation_error",
            meta={"type": exc.__class__.__name__},
        )
    if isinstance(exc, FinalizeError):
        return invariant_violation(
            message=str(exc) or "invariant violation",
            path="$",
            reason="invariant_violation",
            meta={"type": exc.__class__.__name__},
        )
    if isinstance(exc, ModelValidationError):
        return invariant_violation(
            message=str(exc) or "invariant violation",
            path="$",
            reason="invariant_violation",
            meta={"type": exc.__class__.__name__},
        )
    if isinstance(exc, ImportWizardError):
        return error_envelope(
            "INTERNAL_ERROR",
            str(exc) or "internal error",
            details=[
                {
                    "path": "$.error",
                    "reason": "internal_error",
                    "meta": {"type": exc.__class__.__name__},
                }
            ],
        )
    return error_envelope(
        "INTERNAL_ERROR",
        str(exc) or "internal error",
        details=[
            {
                "path": "$.error",
                "reason": "internal_error",
                "meta": {"type": exc.__class__.__name__},
            }
        ],
    )


def _parse_selection_expr(expr: str, *, max_index: int | None) -> list[int]:
    text = expr.strip().lower()
    if text == "all":
        if max_index is None:
            # Caller must provide max_index to expand "all".
            raise ValueError("selection 'all' requires a known max_index")
        return list(range(1, max_index + 1))

    ids: set[int] = set()
    for raw in text.split(","):
        tok = raw.strip()
        if not tok:
            continue
        if "-" in tok:
            parts = [p.strip() for p in tok.split("-", 1)]
            if len(parts) != 2 or not parts[0] or not parts[1]:
                raise ValueError(f"invalid range token: {tok}")
            try:
                start = int(parts[0])
                end = int(parts[1])
            except ValueError as e:
                raise ValueError(f"invalid range token: {tok}") from e
            if start <= 0 or end <= 0 or end < start:
                raise ValueError(f"invalid range token: {tok}")
            for i in range(start, end + 1):
                ids.add(i)
        else:
            try:
                i = int(tok)
            except ValueError as e:
                raise ValueError(f"invalid selection token: {tok}") from e
            if i <= 0:
                raise ValueError(f"invalid selection token: {tok}")
            ids.add(i)

    result = sorted(ids)
    if max_index is not None and any(i > max_index for i in result):
        raise ValueError("selection out of range")
    return result


class ImportWizardEngine:
    """Data-defined import wizard engine."""

    def __init__(self, *, resolver: ConfigResolver | None = None) -> None:
        # Fallback resolver is for tests only. Real hosts must provide a resolver.
        self._resolver = resolver or ConfigResolver(cli_args={})
        self._fs = FileService.from_resolver(self._resolver)

    def get_file_service(self) -> FileService:
        """Return the file service used by this engine.

        This is a plugin-internal helper for CLI/editor tooling.
        """
        return self._fs

    def get_flow_model(self) -> dict[str, Any]:
        """Return FlowModel JSON for the current configuration (spec 10.5)."""
        ensure_default_models(self._fs)
        catalog_dict = read_json(self._fs, RootName.WIZARDS, "import/catalog/catalog.json")
        flow_dict = read_json(self._fs, RootName.WIZARDS, "import/flow/current.json")
        flow_cfg = read_json(self._fs, RootName.WIZARDS, "import/config/flow_config.json")

        flow_cfg_norm = self._normalize_flow_config(flow_cfg)

        catalog = CatalogModel.from_dict(catalog_dict)
        flow = FlowModel.from_dict(flow_dict)
        validate_models(catalog, flow)

        return build_flow_model(catalog=catalog, flow_config=flow_cfg_norm)

    def create_session(
        self,
        root: str,
        relative_path: str,
        *,
        mode: str = "stage",
        flow_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return self._create_session_impl(
                root,
                relative_path,
                mode=mode,
                flow_overrides=flow_overrides,
            )
        except Exception as e:
            return _exception_envelope(e)

    def _create_session_impl(
        self,
        root: str,
        relative_path: str,
        *,
        mode: str = "stage",
        flow_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:

        mode = self._validate_mode(mode)
        # 1) Load models
        _emit("model.load", "model.load", {"root": root, "relative_path": relative_path})
        ensure_default_models(self._fs)
        catalog_dict = read_json(self._fs, RootName.WIZARDS, "import/catalog/catalog.json")
        flow_dict = read_json(self._fs, RootName.WIZARDS, "import/flow/current.json")
        flow_cfg = read_json(self._fs, RootName.WIZARDS, "import/config/flow_config.json")

        flow_cfg_norm = self._normalize_flow_config(flow_cfg)
        if flow_overrides is not None:
            # Legacy testing hook only. Overrides may only toggle optional steps.
            flow_cfg_norm = self._merge_flow_config_overrides(flow_cfg_norm, flow_overrides)

        catalog = CatalogModel.from_dict(catalog_dict)
        flow = FlowModel.from_dict(flow_dict)

        _emit(
            "model.validate",
            "model.validate",
            {"root": root, "relative_path": relative_path},
        )
        validate_models(catalog, flow)

        effective_model = build_flow_model(catalog=catalog, flow_config=flow_cfg_norm)

        # 2) Discovery
        discovery = discovery_mod.run_discovery(self._fs, root=root, relative_path=relative_path)
        discovery_fingerprint = fingerprint_json(discovery)

        authors_items, books_items = _derive_selection_items(discovery)
        effective_model = _inject_selection_items(
            effective_model=effective_model,
            authors_items=authors_items,
            books_items=books_items,
        )

        model_fingerprint = fingerprint_json(effective_model)

        # 3) Effective config snapshot (only keys engine uses)
        effective_config: dict[str, Any] = {
            "version": 1,
            "flow_config": flow_cfg_norm,
            "diagnostics_enabled": bool(self._resolver.resolve("diagnostics.enabled")[0])
            if self._has_key("diagnostics.enabled")
            else False,
        }
        effective_config_fingerprint = fingerprint_json(effective_config)

        # 4) Deterministic session_id
        sid_src = "|".join(
            [
                f"root:{root}",
                f"path:{relative_path}",
                f"mode:{mode}",
                f"m:{model_fingerprint}",
                f"d:{discovery_fingerprint}",
                f"c:{effective_config_fingerprint}",
            ]
        )
        session_id = sha256_hex(sid_src.encode("utf-8"))[:16]

        session_dir = f"import/sessions/{session_id}"
        state_path = f"{session_dir}/state.json"

        if self._fs.exists(RootName.WIZARDS, state_path):
            loaded_state = read_json(self._fs, RootName.WIZARDS, state_path)
            _emit(
                "session.resume",
                "session.resume",
                {
                    "session_id": session_id,
                    "model_fingerprint": loaded_state.get("model_fingerprint"),
                    "discovery_fingerprint": loaded_state.get("derived", {}).get(
                        "discovery_fingerprint"
                    ),
                    "effective_config_fingerprint": loaded_state.get("derived", {}).get(
                        "effective_config_fingerprint"
                    ),
                },
            )
            loaded_state = _ensure_session_state_fields(loaded_state)

            # Best-effort upgrader: ensure persisted effective_model contains selection items.
            # If model changes, update model_fingerprint to match persisted effective_model.
            try:
                em = read_json(
                    self._fs,
                    RootName.WIZARDS,
                    f"{session_dir}/effective_model.json",
                )
                if isinstance(em, dict):
                    before = canonical_serialize(em)
                    em2 = _inject_selection_items(
                        effective_model=em,
                        authors_items=authors_items,
                        books_items=books_items,
                    )
                    after = canonical_serialize(em2)
                    if after != before:
                        atomic_write_json(
                            self._fs,
                            RootName.WIZARDS,
                            f"{session_dir}/effective_model.json",
                            em2,
                        )
                        loaded_state["model_fingerprint"] = fingerprint_json(em2)
                        loaded_state["updated_at"] = _iso_utc_now()
            except Exception:
                pass
            self._persist_state(session_id, loaded_state)
            return loaded_state

        # 5) Persist frozen artifacts
        _emit(
            "session.start",
            "session.start",
            {
                "session_id": session_id,
                "root": root,
                "relative_path": relative_path,
                "mode": mode,
                "model_fingerprint": model_fingerprint,
                "discovery_fingerprint": discovery_fingerprint,
                "effective_config_fingerprint": effective_config_fingerprint,
            },
        )

        atomic_write_json(
            self._fs, RootName.WIZARDS, f"{session_dir}/effective_model.json", effective_model
        )
        atomic_write_json(
            self._fs, RootName.WIZARDS, f"{session_dir}/effective_config.json", effective_config
        )
        atomic_write_json(self._fs, RootName.WIZARDS, f"{session_dir}/discovery.json", discovery)

        atomic_write_text(
            self._fs,
            RootName.WIZARDS,
            f"{session_dir}/discovery_fingerprint.txt",
            discovery_fingerprint + "\n",
        )
        atomic_write_text(
            self._fs,
            RootName.WIZARDS,
            f"{session_dir}/effective_config_fingerprint.txt",
            effective_config_fingerprint + "\n",
        )

        created_at = _iso_utc_now()

        start_step_id = "select_authors"

        state: dict[str, Any] = {
            "session_id": session_id,
            "created_at": created_at,
            "updated_at": created_at,
            "model_fingerprint": model_fingerprint,
            "phase": 1,
            "mode": mode,
            "source": {"root": root, "relative_path": relative_path},
            "current_step_id": start_step_id,
            "completed_step_ids": [],
            "answers": {},
            "inputs": {},
            "computed": {},
            "selected_author_ids": [],
            "selected_book_ids": [],
            "effective_author_title": {},
            "derived": {
                "discovery_fingerprint": discovery_fingerprint,
                "effective_config_fingerprint": effective_config_fingerprint,
                "conflict_fingerprint": "",
            },
            "conflicts": {
                "present": False,
                "items": [],
                "resolved": True,
                "policy": "ask",
            },
            "status": "in_progress",
            "errors": [],
        }

        atomic_write_json(self._fs, RootName.WIZARDS, state_path, state)
        self._append_decision(
            session_id,
            step_id="__system__",
            payload={"event": "session.created", "root": root, "relative_path": relative_path},
            result="accepted",
            error=None,
        )

        return state

    def validate_catalog(self, catalog_json: Any) -> dict[str, Any]:
        """Validate catalog JSON using engine invariants.

        Returns {"ok": True} on success, or a canonical error envelope.
        """
        try:
            if not isinstance(catalog_json, dict):
                raise ValueError("catalog_json must be an object")
            _ = CatalogModel.from_dict(catalog_json)
            return {"ok": True}
        except Exception as e:
            return _exception_envelope(e)

    def validate_flow(self, flow_json: Any, catalog_json: Any) -> dict[str, Any]:
        """Validate flow JSON against the catalog using engine invariants.

        Returns {"ok": True} on success, or a canonical error envelope.
        """
        try:
            if not isinstance(catalog_json, dict):
                raise ValueError("catalog_json must be an object")
            if not isinstance(flow_json, dict):
                raise ValueError("flow_json must be an object")
            catalog = CatalogModel.from_dict(catalog_json)
            flow = FlowModel.from_dict(flow_json)
            validate_models(catalog, flow)
            return {"ok": True}
        except Exception as e:
            return _exception_envelope(e)

    def validate_flow_config(self, flow_config_json: Any) -> dict[str, Any]:
        """Validate FlowConfig JSON.

        FlowConfig v1 governance:
        - version=1
        - optional step toggles only: steps.{step_id}.enabled (bool)
        - required steps may not be disabled
        """
        try:
            if not isinstance(flow_config_json, dict):
                raise ValueError("flow_config_json must be an object")
            _ = self._normalize_flow_config(flow_config_json)
            return {"ok": True}
        except Exception as e:
            return _exception_envelope(e)

    def preview_effective_model(self, catalog_json: Any, flow_json: Any) -> dict[str, Any]:
        """Return the effective model that would be frozen for new sessions."""
        if not isinstance(catalog_json, dict):
            raise ValueError("catalog_json must be an object")
        if not isinstance(flow_json, dict):
            raise ValueError("flow_json must be an object")
        catalog = CatalogModel.from_dict(catalog_json)
        flow = FlowModel.from_dict(flow_json)
        validate_models(catalog, flow)
        flow_cfg = read_json(self._fs, RootName.WIZARDS, "import/config/flow_config.json")
        flow_cfg_norm = self._normalize_flow_config(flow_cfg)
        return build_flow_model(catalog=catalog, flow_config=flow_cfg_norm)

    def _has_key(self, key: str) -> bool:
        try:
            self._resolver.resolve(key)
            return True
        except Exception:
            return False

    def get_state(self, session_id: str) -> dict[str, Any]:
        try:
            return self._load_state(session_id)
        except Exception as e:
            return _exception_envelope(e)

    def get_step_definition(self, session_id: str, step_id: str) -> dict[str, Any]:
        """Return the catalog step definition for step_id.

        This is a UI helper. It does not perform any state transitions.
        """
        try:
            effective_model = self._load_effective_model(session_id)
            steps_any = effective_model.get("steps")
            if not isinstance(steps_any, list):
                raise ValueError("effective model missing steps")
            for step in steps_any:
                if isinstance(step, dict) and step.get("step_id") == step_id:
                    return dict(step)
            raise ValueError("unknown step_id")
        except Exception as e:
            return _exception_envelope(e)

    def submit_step(self, session_id: str, step_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            state = self._load_state(session_id)
            if int(state.get("phase") or 1) == 2:
                raise StepSubmissionError("session is locked (phase 2)")
            if state.get("status") != "in_progress":
                raise StepSubmissionError("session is not in progress")

            _emit(
                "step.submit",
                "step.submit",
                {
                    "session_id": session_id,
                    "step_id": step_id,
                    "model_fingerprint": state.get("model_fingerprint"),
                    "discovery_fingerprint": state.get("derived", {}).get("discovery_fingerprint"),
                    "effective_config_fingerprint": state.get("derived", {}).get(
                        "effective_config_fingerprint"
                    ),
                },
            )

            if not isinstance(payload, dict):
                raise StepSubmissionError("payload must be an object")

            effective_model = self._load_effective_model(session_id)
            steps_any = effective_model.get("steps")
            if not isinstance(steps_any, list):
                raise StepSubmissionError("effective model missing steps")
            steps = [s for s in steps_any if isinstance(s, dict)]
            flow_cfg_norm = self._load_effective_flow_config(session_id)

            step_ids = {str(s.get("step_id")) for s in steps if isinstance(s.get("step_id"), str)}
            if step_id not in step_ids and step_id not in CONDITIONAL_STEP_IDS:
                raise StepSubmissionError("unknown step_id")

            current = str(state.get("current_step_id") or "select_authors")
            if step_id != current:
                raise StepSubmissionError("step_id must match current_step_id")

            schema = None
            for step in steps:
                if step.get("step_id") == step_id:
                    schema = step
                    break
            if schema is None:
                raise StepSubmissionError("unknown step_id")

            if step_id in {"plan_preview_batch", "processing"}:
                raise StepSubmissionError("computed-only step cannot be submitted")

            normalized_payload = self._validate_and_canonicalize_payload(
                step_id=step_id,
                schema=schema,
                payload=payload,
                state=state,
            )

            if step_id == "conflict_policy":
                self._apply_conflict_policy(state, normalized_payload)
            if step_id == "resolve_conflicts_batch":
                self._apply_conflict_resolve(state, normalized_payload)
                self._persist_conflict_resolution(session_id, state, normalized_payload)

            answers = dict(state.get("answers") or {})
            answers[step_id] = normalized_payload
            state["answers"] = answers

            # Backward compatibility: maintain legacy inputs mirror.
            inputs = dict(state.get("inputs") or {})
            inputs[step_id] = normalized_payload
            state["inputs"] = inputs

            if step_id == "select_authors":
                sel = normalized_payload.get("selection")
                if isinstance(sel, list) and all(isinstance(x, str) for x in sel):
                    state["selected_author_ids"] = list(sel)

            if step_id == "select_books":
                sel = normalized_payload.get("selection")
                if isinstance(sel, list) and all(isinstance(x, str) for x in sel):
                    state["selected_book_ids"] = list(sel)

            if step_id == "effective_author_title":
                state["effective_author_title"] = dict(normalized_payload)

            completed = list(state.get("completed_step_ids") or [])
            if step_id not in completed:
                completed.append(step_id)
            state["completed_step_ids"] = completed

            next_step = self._next_step_after_submit(
                step_id=step_id,
                state=state,
                flow_cfg_norm=flow_cfg_norm,
            )

            state["current_step_id"] = self._auto_advance_computed_steps(
                session_id=session_id,
                state=state,
                next_step_id=next_step,
                flow_cfg_norm=flow_cfg_norm,
            )

            state["updated_at"] = _iso_utc_now()
            self._append_decision(
                session_id,
                step_id=step_id,
                payload=normalized_payload,
                result="accepted",
                error=None,
            )
            self._persist_state(session_id, state)
            return state
        except Exception as e:
            self._append_decision(
                session_id,
                step_id=step_id,
                payload=payload if isinstance(payload, dict) else {"_invalid_payload": True},
                result="rejected",
                error={"type": e.__class__.__name__, "message": str(e) or e.__class__.__name__},
            )
            return _exception_envelope(e)

    def _auto_advance_computed_steps(
        self,
        *,
        session_id: str,
        state: dict[str, Any],
        next_step_id: str,
        flow_cfg_norm: dict[str, Any],
    ) -> str:
        """Advance past computed-only steps deterministically (spec 10.3.2/10.3.3).

        Renderers must never be forced to "submit" a computed-only step.
        """

        if next_step_id != "plan_preview_batch":
            return next_step_id

        # plan_preview_batch is computed-only (spec 10.3.1). Compute and advance.
        # Special rule: if plan preview fails due to invalid selection, transition back.
        state["current_step_id"] = "plan_preview_batch"
        self._persist_state(session_id, state)
        try:
            self.compute_plan(session_id)
        except PlanSelectionError:
            state["current_step_id"] = "select_books"
            state["updated_at"] = _iso_utc_now()
            self._persist_state(session_id, state)
            return "select_books"

        except Exception:
            # Non-selection failures must not change the UI state.
            raise

        return self._move_linear(
            current="plan_preview_batch",
            direction="next",
            flow_cfg_norm=flow_cfg_norm,
        )

    def _apply_conflict_policy(self, state: dict[str, Any], payload: dict[str, Any]) -> None:
        raw_mode = payload.get("mode")
        if not isinstance(raw_mode, str) or not raw_mode.strip():
            raise StepSubmissionError("conflict_policy.mode must be a non-empty string")
        mode = raw_mode.strip().lower()
        try:
            mode.encode("ascii")
        except UnicodeEncodeError as e:
            raise StepSubmissionError("conflict_policy.mode must be ASCII-only") from e

        policy = "ask" if mode == "ask" else mode

        conflicts = state.get("conflicts")
        if not isinstance(conflicts, dict):
            conflicts = {}

        conflicts["policy"] = policy

        items = conflicts.get("items")
        present = bool(conflicts.get("present"))
        if isinstance(items, list):
            present = present or bool(items)

        if policy != "ask":
            conflicts["resolved"] = True
        else:
            conflicts["resolved"] = bool(conflicts.get("resolved")) if present else True

        state["conflicts"] = conflicts

    def _apply_conflict_resolve(self, state: dict[str, Any], payload: dict[str, Any]) -> None:
        conflicts = state.get("conflicts")
        if not isinstance(conflicts, dict):
            raise StepSubmissionError("conflicts missing from state")

        policy = str(conflicts.get("policy") or "ask")
        if policy != "ask":
            conflicts["resolved"] = True
            state["conflicts"] = conflicts
            return

        confirm = payload.get("confirm")
        if confirm is not True:
            raise StepSubmissionError("resolve_conflicts_batch.confirm must be true")

        conflicts["resolved"] = True
        state["conflicts"] = conflicts

    def _persist_conflict_resolution(
        self,
        session_id: str,
        state: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        conflicts = state.get("conflicts")
        if not isinstance(conflicts, dict):
            return
        record = {
            "at": _iso_utc_now(),
            "policy": str(conflicts.get("policy") or ""),
            "conflict_fingerprint": str(state.get("derived", {}).get("conflict_fingerprint") or ""),
            "payload": dict(payload),
        }
        session_dir = f"import/sessions/{session_id}"
        atomic_write_json(
            self._fs,
            RootName.WIZARDS,
            f"{session_dir}/conflicts_resolution.json",
            record,
        )

    def _validate_and_canonicalize_payload(
        self,
        *,
        step_id: str,
        schema: dict[str, Any],
        payload: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        fields_any = schema.get("fields")
        if not isinstance(fields_any, list):
            raise StepSubmissionError("step schema is invalid")
        fields: list[dict[str, Any]] = [f for f in fields_any if isinstance(f, dict)]

        allowed: set[str] = set()
        for f in fields:
            name_any = f.get("name")
            ftype_any = f.get("type")
            if not isinstance(name_any, str) or not name_any:
                continue
            allowed.add(name_any)
            if ftype_any == "multi_select_indexed":
                allowed.add(f"{name_any}_expr")
                allowed.add(f"{name_any}_ids")

        unknown = sorted(set(payload.keys()) - allowed)
        if unknown:
            raise StepSubmissionError("unknown field(s): " + ", ".join(unknown))

        normalized: dict[str, Any] = {}
        for f in fields:
            name = f.get("name")
            ftype = f.get("type")
            required = bool(f.get("required"))
            if not isinstance(name, str) or not isinstance(ftype, str):
                continue
            if required and not any(k in payload for k in (name, f"{name}_expr", f"{name}_ids")):
                raise StepSubmissionError(f"missing required field: {name}")

            if ftype in {"toggle", "confirm"}:
                if name not in payload:
                    continue
                value = payload[name]
                if not isinstance(value, bool):
                    raise StepSubmissionError(f"field '{name}' must be bool")
                normalized[name] = value
                continue

            if ftype == "number":
                if name not in payload:
                    continue
                value = payload[name]
                if not isinstance(value, int):
                    raise StepSubmissionError(f"field '{name}' must be int")
                constraints = f.get("constraints")
                if isinstance(constraints, dict):
                    mn = constraints.get("min")
                    mx = constraints.get("max")
                    if isinstance(mn, int) and value < mn:
                        raise StepSubmissionError(f"field '{name}' must be >= {mn}")
                    if isinstance(mx, int) and value > mx:
                        raise StepSubmissionError(f"field '{name}' must be <= {mx}")
                normalized[name] = value
                continue

            if ftype in {"text", "select"}:
                if name not in payload:
                    continue
                value = payload[name]
                if not isinstance(value, str):
                    raise StepSubmissionError(f"field '{name}' must be str")
                normalized[name] = value
                continue

            if ftype == "multi_select_indexed":
                ids = self._canonicalize_multi_select(
                    name=name, field=f, payload=payload, state=state
                )
                normalized[name] = ids
                continue

            if ftype == "table_edit":
                if name not in payload:
                    continue
                value = payload[name]
                if not isinstance(value, list):
                    raise StepSubmissionError(f"field '{name}' must be list")
                normalized[name] = value
                continue

            raise StepSubmissionError(f"unsupported field type: {ftype}")

        return normalized

    def _canonicalize_multi_select(
        self,
        *,
        name: str,
        field: dict[str, Any],
        payload: dict[str, Any],
        state: dict[str, Any],
    ) -> list[str]:
        # Source items are taken from field.items when present, otherwise from discovery.
        items: list[dict[str, Any]] = []
        items_any = field.get("items")
        if (
            isinstance(items_any, list)
            and items_any
            and all(isinstance(x, dict) for x in items_any)
        ):
            items = [cast(dict[str, Any], x) for x in items_any]
        else:
            session_dir = f"import/sessions/{state.get('session_id')}"
            discovery_any = read_json(self._fs, RootName.WIZARDS, f"{session_dir}/discovery.json")
            if isinstance(discovery_any, list) and all(isinstance(x, dict) for x in discovery_any):
                items = [cast(dict[str, Any], x) for x in discovery_any]

        ordered_ids: list[str] = []
        for it in items:
            item_id = it.get("item_id")
            if isinstance(item_id, str):
                ordered_ids.append(item_id)

        if not ordered_ids:
            raise StepSubmissionError(f"field '{name}' has no selectable items")

        if f"{name}_ids" in payload:
            raw = payload.get(f"{name}_ids")
            if not (isinstance(raw, list) and all(isinstance(x, str) for x in raw)):
                raise StepSubmissionError(f"field '{name}_ids' must be list[str]")
            requested = [str(x) for x in raw]
            unknown = sorted({x for x in requested if x not in set(ordered_ids)})
            if unknown:
                raise StepSubmissionError(f"unknown id(s) in '{name}_ids'")
            # Stable selection: preserve discovery order.
            selected_set = set(requested)
            return [x for x in ordered_ids if x in selected_set]

        expr_key = f"{name}_expr"
        if expr_key not in payload and name in payload and isinstance(payload.get(name), str):
            # Backward compatibility: allow a plain string value as expr.
            payload = dict(payload)
            payload[expr_key] = payload[name]

        if expr_key not in payload:
            raise StepSubmissionError(f"missing '{expr_key}' or '{name}_ids'")
        expr = payload.get(expr_key)
        if not isinstance(expr, str):
            raise StepSubmissionError(f"field '{expr_key}' must be str")

        indices = _parse_selection_expr(expr, max_index=len(ordered_ids))
        # Stable selection: preserve discovery order while honoring indices.
        selected_indices = set(indices)
        selected_ids: list[str] = []
        for idx, item_id in enumerate(ordered_ids, start=1):
            if idx in selected_indices:
                selected_ids.append(item_id)
        return selected_ids

    def apply_action(self, session_id: str, action: str) -> dict[str, Any]:
        try:
            state = self._load_state(session_id)
            if int(state.get("phase") or 1) == 2:
                return invariant_violation(
                    message="session is locked (phase 2)",
                    path="$.phase",
                    reason="phase_locked",
                    meta={},
                )
            if state.get("status") != "in_progress":
                return invariant_violation(
                    message="session is not in progress",
                    path="$.status",
                    reason="status_not_in_progress",
                    meta={},
                )

            action = str(action)
            if action not in {"next", "back", "cancel"}:
                raise StepSubmissionError("invalid action")

            if action == "cancel":
                state["status"] = "aborted"
                state["updated_at"] = _iso_utc_now()
                self._append_decision(
                    session_id,
                    step_id="__system__",
                    payload={"action": "cancel"},
                    result="accepted",
                    error=None,
                )
                self._persist_state(session_id, state)
                return state

            flow_cfg_norm = self._load_effective_flow_config(session_id)
            current = str(state.get("current_step_id") or "select_authors")
            direction = "next" if action == "next" else "back"

            next_step_id = self._move_linear(
                current=current,
                direction=direction,
                flow_cfg_norm=flow_cfg_norm,
            )

            if direction == "next":
                state["current_step_id"] = self._auto_advance_computed_steps(
                    session_id=session_id,
                    state=state,
                    next_step_id=next_step_id,
                    flow_cfg_norm=flow_cfg_norm,
                )
            else:
                # Computed-only steps must not be the UI current step.
                if next_step_id == "plan_preview_batch":
                    state["current_step_id"] = "select_books"
                else:
                    state["current_step_id"] = next_step_id

            state["updated_at"] = _iso_utc_now()
            self._append_decision(
                session_id,
                step_id="__system__",
                payload={"action": action, "from": current, "to": state.get("current_step_id")},
                result="accepted",
                error=None,
            )
            self._persist_state(session_id, state)
            return state
        except Exception as e:
            return _exception_envelope(e)

    def compute_plan(self, session_id: str) -> dict[str, Any]:
        state = self._load_state(session_id)

        _emit(
            "plan.compute",
            "plan.compute",
            {
                "session_id": session_id,
                "model_fingerprint": state.get("model_fingerprint"),
                "discovery_fingerprint": state.get("derived", {}).get("discovery_fingerprint"),
                "effective_config_fingerprint": state.get("derived", {}).get(
                    "effective_config_fingerprint"
                ),
            },
        )

        session_dir = f"import/sessions/{session_id}"
        discovery = read_json(self._fs, RootName.WIZARDS, f"{session_dir}/discovery.json")
        src = state.get("source") or {}
        src_root = str(src.get("root") or "")
        src_rel = str(src.get("relative_path") or "")
        plan = compute_plan(
            session_id=session_id,
            root=src_root,
            relative_path=src_rel,
            discovery=discovery,
            inputs=dict(state.get("answers") or {}),
            selected_book_ids=list(state.get("selected_book_ids") or []),
        )
        atomic_write_json(self._fs, RootName.WIZARDS, f"{session_dir}/plan.json", plan)

        computed = dict(state.get("computed") or {})
        summary_any = plan.get("summary") if isinstance(plan, dict) else None
        sel_any = plan.get("selected_policies") if isinstance(plan, dict) else None
        summary = summary_any if isinstance(summary_any, dict) else {}
        selected_policies = sel_any if isinstance(sel_any, dict) else {}
        computed["plan_summary"] = {
            "files": int(summary.get("files") or 0),
            "dirs": int(summary.get("dirs") or 0),
            "bundles": int(summary.get("bundles") or 0),
            "selected_policies": dict(selected_policies),
        }
        state["computed"] = computed

        # Update conflict fingerprint during plan preview.
        self._update_conflicts(session_id, state)
        state["updated_at"] = _iso_utc_now()
        self._append_decision(
            session_id,
            step_id="__system__",
            payload={"event": "plan.computed"},
            result="accepted",
            error=None,
        )
        self._persist_state(session_id, state)
        return plan

    def finalize(self, session_id: str) -> dict[str, Any]:
        # finalize() is a legacy entry point kept for compatibility.
        # Per spec: job_requests.json may only be created by start_processing(confirm=true).
        return invariant_violation(
            message="finalize is not supported; use start_processing(confirm=true)",
            path="$.finalize",
            reason="legacy_operation",
            meta={},
        )

    def start_processing(self, session_id: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            state = self._load_state(session_id)
            if int(state.get("phase") or 1) == 2:
                return self._start_processing_idempotent(session_id, state, body)
            if state.get("status") != "in_progress":
                raise FinalizeError("session is not active")

            if not isinstance(body, dict):
                raise ValueError("body must be an object")
            confirm = body.get("confirm")
            if confirm is not True:
                return validation_error(
                    message="confirm must be true",
                    path="$.confirm",
                    reason="missing_or_false",
                    meta={},
                )

            runtime_inputs = dict(state.get("inputs") or {})
            final = runtime_inputs.get("final_summary_confirm")
            if not (isinstance(final, dict) and final.get("confirm_start") is True):
                return validation_error(
                    message="final_summary_confirm must be submitted with confirm=true",
                    path="$.inputs.final_summary_confirm.confirm_start",
                    reason="missing_or_false",
                    meta={},
                )

            _emit(
                "finalize.request",
                "finalize.request",
                {
                    "session_id": session_id,
                    "mode": str(state.get("mode") or ""),
                    "model_fingerprint": str(state.get("model_fingerprint") or ""),
                    "discovery_fingerprint": str(
                        state.get("derived", {}).get("discovery_fingerprint") or ""
                    ),
                    "effective_config_fingerprint": str(
                        state.get("derived", {}).get("effective_config_fingerprint") or ""
                    ),
                    "conflict_fingerprint": str(
                        state.get("derived", {}).get("conflict_fingerprint") or ""
                    ),
                },
            )

            # Conflict policy re-check.
            # Must be based on a fresh deterministic scan immediately before job creation.
            conflicts = state.get("conflicts")
            policy = str(conflicts.get("policy") or "ask") if isinstance(conflicts, dict) else "ask"
            preview_fp = str(state.get("derived", {}).get("conflict_fingerprint") or "")

            current_conflicts = self._scan_conflicts(session_id, state)
            current_fp = fingerprint_json(current_conflicts)

            resolved = self._resolve_flag_for_scan(
                state=state,
                policy=policy,
                current_fp=current_fp,
                current_conflicts=current_conflicts,
            )

            # Persist current conflicts to session state (UI must see the latest scan).
            state.setdefault("derived", {})["conflict_fingerprint"] = current_fp
            state["conflicts"] = {
                "present": bool(current_conflicts),
                "items": current_conflicts,
                "resolved": resolved,
                "policy": str((state.get("conflicts") or {}).get("policy") or "ask"),
            }
            session_dir = f"import/sessions/{session_id}"
            atomic_write_json(
                self._fs,
                RootName.WIZARDS,
                f"{session_dir}/conflicts.json",
                current_conflicts,
            )
            state["updated_at"] = _iso_utc_now()
            self._persist_state(session_id, state)

            if policy == "ask" and current_conflicts and not resolved:
                return error_envelope(
                    "CONFLICTS_UNRESOLVED",
                    "conflicts must be resolved before processing",
                    details=[
                        {
                            "path": "$.conflicts",
                            "reason": "conflicts_unresolved",
                            "meta": {"policy": policy},
                        }
                    ],
                )

            if policy != "ask" and preview_fp and current_fp != preview_fp:
                return invariant_violation(
                    message="conflict scan changed since preview",
                    path="$.conflicts",
                    reason="conflicts_changed",
                    meta={"preview": preview_fp, "current": current_fp},
                )

            # Ensure plan exists.
            plan_path = f"{session_dir}/plan.json"
            if self._fs.exists(RootName.WIZARDS, plan_path):
                plan = read_json(self._fs, RootName.WIZARDS, plan_path)
            else:
                plan = self.compute_plan(session_id)

            src = state.get("source") or {}
            src_root = str(src.get("root") or "")
            src_rel = str(src.get("relative_path") or "")
            diagnostics_context = {
                "model_fingerprint": str(state.get("model_fingerprint") or ""),
                "discovery_fingerprint": str(
                    state.get("derived", {}).get("discovery_fingerprint") or ""
                ),
                "effective_config_fingerprint": str(
                    state.get("derived", {}).get("effective_config_fingerprint") or ""
                ),
                "conflict_fingerprint": str(
                    state.get("derived", {}).get("conflict_fingerprint") or ""
                ),
            }

            policy_inputs = dict(state.get("answers") or {})
            job_requests = build_job_requests(
                session_id=session_id,
                root=src_root,
                relative_path=src_rel,
                mode=str(state.get("mode") or ""),
                diagnostics_context=diagnostics_context,
                config_fingerprint=str(
                    state.get("derived", {}).get("effective_config_fingerprint") or ""
                ),
                plan=plan,
                inputs=policy_inputs,
            )

            job_path = f"{session_dir}/job_requests.json"
            job_bytes = canonical_serialize(job_requests)
            atomic_write_text(self._fs, RootName.WIZARDS, job_path, job_bytes.decode("utf-8"))

            idem_key = str(job_requests.get("idempotency_key") or "")
            job_id = self._get_or_create_job(session_id, state, idem_key)

            self._enter_phase_2(session_id, state)

            _emit(
                "job.create",
                "job.create",
                {
                    "session_id": session_id,
                    "job_id": job_id,
                    "idempotency_key": idem_key,
                    "mode": str(state.get("mode") or ""),
                    "model_fingerprint": str(state.get("model_fingerprint") or ""),
                    "discovery_fingerprint": str(
                        state.get("derived", {}).get("discovery_fingerprint") or ""
                    ),
                    "effective_config_fingerprint": str(
                        state.get("derived", {}).get("effective_config_fingerprint") or ""
                    ),
                    "conflict_fingerprint": str(
                        state.get("derived", {}).get("conflict_fingerprint") or ""
                    ),
                },
            )

            from .job_requests import planned_units_count

            batch_size = planned_units_count(plan)
            return {"job_ids": [job_id], "batch_size": batch_size}
        except Exception as e:
            return _exception_envelope(e)

    def _start_processing_idempotent(
        self, session_id: str, state: dict[str, Any], body: dict[str, Any]
    ) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise ValueError("body must be an object")
        confirm = body.get("confirm")
        if confirm is not True:
            return validation_error(
                message="confirm must be true",
                path="$.confirm",
                reason="missing_or_false",
                meta={},
            )

        session_dir = f"import/sessions/{session_id}"
        job_path = f"{session_dir}/job_requests.json"
        if not self._fs.exists(RootName.WIZARDS, job_path):
            raise FinalizeError("job_requests.json is missing")

        job_requests_any = read_json(self._fs, RootName.WIZARDS, job_path)
        if not isinstance(job_requests_any, dict):
            raise FinalizeError("job_requests.json is invalid")
        idem_key = str(job_requests_any.get("idempotency_key") or "")
        if not idem_key:
            raise FinalizeError("job_requests.json missing idempotency_key")

        job_id = self._get_or_create_job(session_id, state, idem_key)
        plan_path = f"{session_dir}/plan.json"
        plan = (
            read_json(self._fs, RootName.WIZARDS, plan_path)
            if self._fs.exists(RootName.WIZARDS, plan_path)
            else {}
        )
        if not isinstance(plan, dict):
            plan = {}
        from .job_requests import planned_units_count

        return {"job_ids": [job_id], "batch_size": planned_units_count(plan)}

    def _resolve_flag_for_scan(
        self,
        *,
        state: dict[str, Any],
        policy: str,
        current_fp: str,
        current_conflicts: list[dict[str, Any]],
    ) -> bool:
        if policy != "ask":
            return True
        if not current_conflicts:
            return True

        prev = state.get("conflicts")
        prev_resolved = bool(prev.get("resolved")) if isinstance(prev, dict) else False
        prev_fp = str(state.get("derived", {}).get("conflict_fingerprint") or "")
        if current_fp != prev_fp:
            return False
        return prev_resolved

    def _enter_phase_2(self, session_id: str, state: dict[str, Any]) -> None:
        effective_model = self._load_effective_model(session_id)
        catalog_any = effective_model.get("catalog")
        step_ids: set[str] = set()
        if isinstance(catalog_any, dict):
            try:
                catalog = CatalogModel.from_dict(cast(dict[str, Any], catalog_any))
                step_ids = catalog.step_ids()
            except Exception:
                step_ids = set()

        if "processing" in step_ids:
            state["current_step_id"] = "processing"

        state["phase"] = 2
        state["status"] = "processing"
        state["updated_at"] = _iso_utc_now()
        self._persist_state(session_id, state)

    def _validate_mode(self, mode: str) -> str:
        mode = str(mode)
        if mode not in {"stage", "inplace"}:
            raise ValueError("mode must be 'stage' or 'inplace'")
        return mode

    def _load_effective_flow_config(self, session_id: str) -> dict[str, Any]:
        session_dir = f"import/sessions/{session_id}"
        cfg_any = read_json(self._fs, RootName.WIZARDS, f"{session_dir}/effective_config.json")
        if not isinstance(cfg_any, dict):
            return {"version": 1, "steps": {}, "defaults": {}, "ui": {}}
        flow_cfg_any = cfg_any.get("flow_config")
        if not isinstance(flow_cfg_any, dict):
            return {"version": 1, "steps": {}, "defaults": {}, "ui": {}}
        return flow_cfg_any

    def _linear_enabled_steps(self, flow_cfg_norm: dict[str, Any]) -> list[str]:
        steps: list[str] = []
        for sid in CANONICAL_STEP_ORDER:
            if sid in FLOWCFG_OPTIONAL_STEP_IDS and not self._is_step_enabled(sid, flow_cfg_norm):
                continue
            steps.append(sid)
        return steps

    def _move_linear(
        self,
        *,
        current: str,
        direction: str,
        flow_cfg_norm: dict[str, Any],
    ) -> str:
        linear = self._linear_enabled_steps(flow_cfg_norm)
        if not linear:
            return "select_authors"
        if current not in linear:
            return linear[0]
        idx = linear.index(current)
        if direction == "next":
            return linear[min(idx + 1, len(linear) - 1)]
        return linear[max(idx - 1, 0)]

    def _next_step_after_submit(
        self,
        *,
        step_id: str,
        state: dict[str, Any],
        flow_cfg_norm: dict[str, Any],
    ) -> str:
        # Spec 10.3.4 conditional conflict path.
        if step_id == "resolve_conflicts_batch":
            return "final_summary_confirm"

        if step_id == "final_summary_confirm":
            inputs = state.get("inputs") or {}
            payload = inputs.get("final_summary_confirm") if isinstance(inputs, dict) else None
            confirm = payload.get("confirm_start") if isinstance(payload, dict) else None
            if confirm is not True:
                return "final_summary_confirm"

            conflicts = state.get("conflicts")
            policy = "ask"
            if isinstance(conflicts, dict):
                policy = str(conflicts.get("policy") or "ask")

            if policy != "ask":
                return "processing"

            # conflict_mode == ask: perform deterministic scan here (spec 10.3.4).
            self._update_conflicts(str(state.get("session_id") or ""), state)
            conflicts2 = state.get("conflicts")
            present = bool(conflicts2.get("present")) if isinstance(conflicts2, dict) else False
            resolved = bool(conflicts2.get("resolved")) if isinstance(conflicts2, dict) else True
            if present and not resolved:
                return "resolve_conflicts_batch"
            return "processing"

        # Default: strictly linear ordering, skipping disabled optional steps (spec 10.3.2).
        return self._move_linear(current=step_id, direction="next", flow_cfg_norm=flow_cfg_norm)

    def _is_step_enabled(self, step_id: str, flow_cfg_norm: dict[str, Any]) -> bool:
        steps_any = flow_cfg_norm.get("steps")
        if not isinstance(steps_any, dict):
            return True
        cfg_any = steps_any.get(step_id)
        if not isinstance(cfg_any, dict):
            return True
        enabled = cfg_any.get("enabled")
        if enabled is None:
            return True
        return bool(enabled)

    def _coerce_start_step(self, flow: FlowModel, flow_cfg_norm: dict[str, Any]) -> str:
        entry = str(flow.entry_step_id)
        if self._is_step_enabled(entry, flow_cfg_norm):
            return entry
        next_enabled = self._next_enabled_step(
            flow, entry, direction="next", flow_cfg_norm=flow_cfg_norm
        )
        return next_enabled or entry

    def _next_enabled_step(
        self,
        flow: FlowModel,
        from_step_id: str,
        *,
        direction: str,
        flow_cfg_norm: dict[str, Any],
    ) -> str | None:
        if direction not in {"next", "back"}:
            raise ValueError("direction must be 'next' or 'back'")

        node_map = flow.node_map()
        visited: set[str] = set()
        cur = from_step_id
        while True:
            if cur in visited:
                return None
            visited.add(cur)

            node = node_map.get(cur)
            if node is None:
                return None
            candidate = node.next_step_id if direction == "next" else node.prev_step_id
            if candidate is None:
                return None
            if self._is_step_enabled(candidate, flow_cfg_norm):
                return candidate
            cur = candidate

    def _normalize_flow_config(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise ValueError("flow_config must be an object")
        version = raw.get("version")
        if version != 1:
            raise ValueError("flow_config.version must be 1")

        steps_any = raw.get("steps", {})
        if steps_any is None:
            steps_any = {}
        if not isinstance(steps_any, dict):
            raise ValueError("flow_config.steps must be an object")

        steps: dict[str, Any] = {}
        for step_id, cfg in steps_any.items():
            if not isinstance(step_id, str) or not step_id:
                raise ValueError("flow_config.steps keys must be non-empty strings")
            if not isinstance(cfg, dict):
                raise ValueError("flow_config.steps.<step_id> must be an object")
            enabled = cfg.get("enabled")
            if enabled is not None and not isinstance(enabled, bool):
                raise ValueError("flow_config.steps.<step_id>.enabled must be bool")
            if enabled is False and step_id in BASE_REQUIRED_STEP_IDS:
                raise FinalizeError(f"required step may not be disabled: {step_id}")
            if enabled is None:
                continue
            steps[step_id] = {"enabled": bool(enabled)}

        defaults_any = raw.get("defaults", {})
        ui_any = raw.get("ui", {})
        if defaults_any is None:
            defaults_any = {}
        if ui_any is None:
            ui_any = {}
        if not isinstance(defaults_any, dict):
            raise ValueError("flow_config.defaults must be an object")
        if not isinstance(ui_any, dict):
            raise ValueError("flow_config.ui must be an object")

        return {"version": 1, "steps": steps, "defaults": defaults_any, "ui": ui_any}

    def _merge_flow_config_overrides(
        self, base: dict[str, Any], overrides: dict[str, Any]
    ) -> dict[str, Any]:
        if not isinstance(overrides, dict):
            raise ValueError("flow_overrides must be an object")
        if "steps" not in overrides:
            return base
        merged = dict(base)
        steps = dict(cast(dict[str, Any], merged.get("steps") or {}))
        raw_steps = overrides.get("steps")
        if not isinstance(raw_steps, dict):
            raise ValueError("flow_overrides.steps must be an object")
        for step_id, cfg in raw_steps.items():
            if not isinstance(step_id, str) or not step_id:
                raise ValueError("flow_overrides.steps keys must be strings")
            if not isinstance(cfg, dict):
                raise ValueError("flow_overrides.steps.<step_id> must be an object")
            enabled = cfg.get("enabled")
            if enabled is None:
                continue
            if not isinstance(enabled, bool):
                raise ValueError("flow_overrides.steps.<step_id>.enabled must be bool")
            if enabled is False and step_id in BASE_REQUIRED_STEP_IDS:
                raise FinalizeError(f"required step may not be disabled: {step_id}")
            steps[step_id] = {"enabled": bool(enabled)}
        merged["steps"] = steps
        return merged

    def _scan_conflicts(self, session_id: str, state: dict[str, Any]) -> list[dict[str, str]]:
        from .conflicts import scan_conflicts

        session_dir = f"import/sessions/{session_id}"
        plan_path = f"{session_dir}/plan.json"
        if not self._fs.exists(RootName.WIZARDS, plan_path):
            _ = self.compute_plan(session_id)

        plan = read_json(self._fs, RootName.WIZARDS, plan_path)
        if not isinstance(plan, dict):
            plan = {}

        mode = self._validate_mode(str(state.get("mode") or "stage"))
        items = scan_conflicts(self._fs, plan=plan, mode=mode)
        return [cast(dict[str, str], it) for it in items]

    def _update_conflicts(self, session_id: str, state: dict[str, Any]) -> None:
        items = self._scan_conflicts(session_id, state)
        fp = fingerprint_json(items)
        policy = str((state.get("conflicts") or {}).get("policy") or "ask")
        resolved = self._resolve_flag_for_scan(
            state=state,
            policy=policy,
            current_fp=fp,
            current_conflicts=items,
        )

        state.setdefault("derived", {})["conflict_fingerprint"] = fp
        state["conflicts"] = {
            "present": bool(items),
            "items": items,
            "resolved": resolved,
            "policy": policy,
        }
        session_dir = f"import/sessions/{session_id}"
        atomic_write_json(self._fs, RootName.WIZARDS, f"{session_dir}/conflicts.json", items)

    def _get_or_create_job(self, session_id: str, state: dict[str, Any], idem_key: str) -> str:
        session_dir = f"import/sessions/{session_id}"
        idem_path = f"{session_dir}/idempotency.json"
        mapping: dict[str, str] = {}
        if self._fs.exists(RootName.WIZARDS, idem_path):
            loaded = read_json(self._fs, RootName.WIZARDS, idem_path)
            if isinstance(loaded, dict):
                mapping = {str(k): str(v) for k, v in loaded.items()}

        if idem_key in mapping and mapping[idem_key]:
            return mapping[idem_key]

        from audiomason.core.jobs.api import JobService
        from audiomason.core.jobs.model import JobType

        meta = {
            "source": "import",
            "session_id": session_id,
            "idempotency_key": idem_key,
            "effective_config_fingerprint": str(
                state.get("derived", {}).get("effective_config_fingerprint") or ""
            ),
            "model_fingerprint": str(state.get("model_fingerprint") or ""),
            "discovery_fingerprint": str(
                state.get("derived", {}).get("discovery_fingerprint") or ""
            ),
            "job_requests_path": f"wizards:{session_dir}/job_requests.json",
        }
        job = JobService().create_job(JobType.PROCESS, meta=meta)
        mapping[idem_key] = job.job_id
        atomic_write_json(self._fs, RootName.WIZARDS, idem_path, mapping)
        return job.job_id

    def _load_state(self, session_id: str) -> dict[str, Any]:
        session_dir = f"import/sessions/{session_id}"
        state_path = f"{session_dir}/state.json"
        if not self._fs.exists(RootName.WIZARDS, state_path):
            raise SessionNotFoundError(f"session not found: {session_id}")
        state = read_json(self._fs, RootName.WIZARDS, state_path)
        if isinstance(state, dict):
            state = _ensure_session_state_fields(state)
            self._persist_state(session_id, state)
        return state

    def _persist_state(self, session_id: str, state: dict[str, Any]) -> None:
        session_dir = f"import/sessions/{session_id}"
        atomic_write_json(self._fs, RootName.WIZARDS, f"{session_dir}/state.json", state)

    def _load_effective_model(self, session_id: str) -> dict[str, Any]:
        session_dir = f"import/sessions/{session_id}"
        return read_json(self._fs, RootName.WIZARDS, f"{session_dir}/effective_model.json")

    def _append_decision(
        self,
        session_id: str,
        *,
        step_id: str,
        payload: dict[str, Any],
        result: str,
        error: dict[str, Any] | None,
    ) -> None:
        session_dir = f"import/sessions/{session_id}"
        entry: dict[str, Any] = {
            "at": _iso_utc_now(),
            "step_id": step_id,
            "payload": dict(payload),
            "result": result,
        }
        if error is not None:
            entry["error"] = dict(error)
        append_jsonl(self._fs, RootName.WIZARDS, f"{session_dir}/decisions.jsonl", entry)
