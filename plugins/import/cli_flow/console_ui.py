"""Console UI implementation for import CLI.

Rules (Issue 600):
- This module contains only rendering and input collection.
- It must not contain detection/guessing/business logic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConsoleUI:
    """Synchronous console UI helpers."""

    def print(self, text: str = "") -> None:
        print(text)

    def select(self, prompt: str, options: list[str], default_index: int = 1) -> str | None:
        if not options:
            return None

        # Clamp default into range; default selection is deterministic.
        if default_index < 1:
            default_index = 1
        if default_index > len(options):
            default_index = len(options)

        while True:
            self.print("\n" + prompt)
            for n, opt in enumerate(options, 1):
                self.print(f"  {n}. {opt}")

            raw = input(f"Select (default {default_index}; q to quit): ").strip()
            if raw.lower() in {"q", "quit", "exit"}:
                return None

            if not raw:
                return options[default_index - 1]

            if raw.isdigit():
                k = int(raw)
                if 1 <= k <= len(options):
                    return options[k - 1]

            self.print("Invalid selection")

    def prompt_text(self, prompt: str, default: str) -> str:
        raw = input(f"{prompt} [{default}]: ").strip()
        return raw if raw else default

    def confirm(self, prompt: str, *, default: bool = False) -> bool:
        suffix = "[Y/n]" if default else "[y/N]"
        raw = input(f"{prompt} {suffix}: ").strip().lower()
        if not raw:
            return default
        return raw in {"y", "yes"}
