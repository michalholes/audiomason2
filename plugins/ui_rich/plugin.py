"""Rich UI plugin - enhanced visual output.

Features:
- Progress bars with Rich library
- Colored output
- Better formatting
- Status display
"""

from __future__ import annotations

from typing import Any


class RichUIPlugin:
    """Rich UI enhancements.

    Note: This is a simplified version that works without Rich library.
    For full Rich support, install: pip install rich
    """

    def __init__(self, config: dict | None = None) -> None:
        """Initialize plugin.

        Args:
            config: Plugin configuration
        """
        self.config = config or {}
        self.color = self.config.get("color", True)

        # Try to import Rich
        try:
            from rich.console import Console
            from rich.panel import Panel
            from rich.progress import (
                BarColumn,
                Progress,
                SpinnerColumn,
                TextColumn,
                TimeRemainingColumn,
            )
            from rich.table import Table

            self.has_rich = True
            self.console: Console | None = Console()
            self._Progress = Progress
            self._SpinnerColumn = SpinnerColumn
            self._BarColumn = BarColumn
            self._TextColumn = TextColumn
            self._TimeRemainingColumn = TimeRemainingColumn
            self._Table = Table
            self._Panel = Panel
        except ImportError:
            self.has_rich = False
            self.console: Console | None = None

    def print_header(self, text: str) -> None:
        """Print header with formatting.

        Args:
            text: Header text
        """
        if self.has_rich and self.console:
            from rich.panel import Panel

            self.console.print(Panel(f"[bold cyan]{text}[/bold cyan]"))
        else:
            print(f"\n{'=' * 70}")
            print(f" {text}")
            print(f"{'=' * 70}\n")

    def print_success(self, text: str) -> None:
        """Print success message.

        Args:
            text: Success text
        """
        if self.has_rich and self.console:
            self.console.print(f"[bold green]✓[/bold green] {text}")
        else:
            print(f"✓ {text}")

    def print_error(self, text: str) -> None:
        """Print error message.

        Args:
            text: Error text
        """
        if self.has_rich and self.console:
            self.console.print(f"[bold red]✗[/bold red] {text}")
        else:
            print(f"✗ {text}")

    def print_warning(self, text: str) -> None:
        """Print warning message.

        Args:
            text: Warning text
        """
        if self.has_rich and self.console:
            self.console.print(f"[bold yellow]⚠[/bold yellow] {text}")
        else:
            print(f"⚠ {text}")

    def print_info(self, text: str) -> None:
        """Print info message.

        Args:
            text: Info text
        """
        if self.has_rich and self.console:
            self.console.print(f"[bold blue]ℹ[/bold blue] {text}")
        else:
            print(f"ℹ {text}")

    def create_progress(self) -> Any:
        """Create progress bar.

        Returns:
            Progress bar object (or None if Rich not available)
        """
        if self.has_rich:
            return self._Progress(
                self._SpinnerColumn(),
                self._TextColumn("[progress.description]{task.description}"),
                self._BarColumn(),
                self._TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                self._TimeRemainingColumn(),
            )
        return None

    def print_table(self, title: str, headers: list[str], rows: list[list[str]]) -> None:
        """Print formatted table.

        Args:
            title: Table title
            headers: Column headers
            rows: Table rows
        """
        if self.has_rich and self.console:
            table = self._Table(title=title)

            for header in headers:
                table.add_column(header, style="cyan")

            for row in rows:
                table.add_row(*row)

            self.console.print(table)
        else:
            # Fallback to simple formatting
            print(f"\n{title}")
            print("-" * 70)
            print(" | ".join(headers))
            print("-" * 70)
            for row in rows:
                print(" | ".join(row))
            print()

    def print_status(self, contexts: list[Any]) -> None:
        """Print status for multiple books.

        Args:
            contexts: List of ProcessingContext objects
        """
        if self.has_rich and self.console:
            from rich.table import Table

            table = Table(title="Processing Status")
            table.add_column("Book", style="cyan")
            table.add_column("Status", style="yellow")
            table.add_column("Progress", style="green")

            for ctx in contexts:
                status = ctx.state.value if hasattr(ctx, "state") else "unknown"
                progress = f"{ctx.progress * 100:.0f}%" if hasattr(ctx, "progress") else "0%"
                title = getattr(ctx, "title", "Unknown")

                table.add_row(title, status, progress)

            self.console.print(table)
        else:
            # Fallback
            print("\nProcessing Status:")
            print("-" * 70)
            for i, ctx in enumerate(contexts, 1):
                title = getattr(ctx, "title", "Unknown")
                status = ctx.state.value if hasattr(ctx, "state") else "unknown"
                progress = f"{ctx.progress * 100:.0f}%" if hasattr(ctx, "progress") else "0%"
                print(f"{i}. {title:30s} {status:15s} {progress:>6s}")
            print()


# Global instance
_ui_plugin: RichUIPlugin | None = None


def get_ui() -> RichUIPlugin:
    """Get global UI plugin instance.

    Returns:
        RichUIPlugin instance
    """
    global _ui_plugin
    if _ui_plugin is None:
        _ui_plugin = RichUIPlugin()
    return _ui_plugin
