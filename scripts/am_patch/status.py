from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass


@dataclass
class StatusState:
    stage: str = "PREFLIGHT"
    started: float = 0.0


class StatusReporter:
    """Best-effort progress indicator.

    - In TTY: updates a single line on stderr using carriage return.
    - In non-TTY: prints periodic heartbeat lines to stderr.
    - Intended to be silent when disabled (e.g. verbosity=quiet).
    """

    def __init__(
        self,
        *,
        enabled: bool,
        interval_tty: float = 1.0,
        interval_non_tty: float = 30.0,
    ) -> None:
        self._enabled = enabled
        self._interval_tty = interval_tty
        self._interval_non_tty = interval_non_tty
        self._state = StatusState(stage="PREFLIGHT", started=time.monotonic())
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self._enabled:
            return
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="am_patch_status", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._enabled:
            return
        self._stop.set()
        t = self._thread
        if t is not None:
            t.join(timeout=2.0)
        self._thread = None
        if sys.stderr.isatty():
            # Clear the status line.
            sys.stderr.write("\r\n")
            sys.stderr.flush()

    def set_stage(self, stage: str) -> None:
        if not self._enabled:
            return
        with self._lock:
            self._state.stage = stage

    def _elapsed_mmss(self) -> str:
        with self._lock:
            started = self._state.started
        elapsed = max(0.0, time.monotonic() - started)
        mm = int(elapsed // 60)
        ss = int(elapsed % 60)
        return f"{mm:02d}:{ss:02d}"

    def _render_tty(self) -> None:
        with self._lock:
            stage = self._state.stage
        msg = f"STATUS: {stage}  ELAPSED: {self._elapsed_mmss()}"
        sys.stderr.write("\r" + msg)
        sys.stderr.flush()

    def _render_non_tty(self) -> None:
        with self._lock:
            stage = self._state.stage
        sys.stderr.write(f"HEARTBEAT: {stage} elapsed={self._elapsed_mmss()}\n")
        sys.stderr.flush()

    def _run(self) -> None:
        is_tty = sys.stderr.isatty()
        interval = self._interval_tty if is_tty else self._interval_non_tty
        # First tick quickly so user sees it.
        next_tick = time.monotonic()
        while not self._stop.is_set():
            now = time.monotonic()
            if now >= next_tick:
                if is_tty:
                    self._render_tty()
                else:
                    self._render_non_tty()
                next_tick = now + interval
            self._stop.wait(0.2)
