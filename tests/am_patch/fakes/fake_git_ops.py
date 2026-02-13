from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeGitOps:
    """Record git operations for higher-level tests."""

    committed_messages: list[str] = field(default_factory=list)
    pushed: int = 0

    def commit(self, message: str) -> None:
        self.committed_messages.append(message)

    def push(self) -> None:
        self.pushed += 1
