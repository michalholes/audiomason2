"""Example plugin demonstrating the plugin system."""

from audiomason.core import ProcessingContext


class ExamplePlugin:
    """Example plugin that implements IProcessor interface."""

    def __init__(self, config: dict | None = None) -> None:
        """Initialize plugin.

        Args:
            config: Plugin configuration
        """
        self.config = config or {}
        self.message = self.config.get("message", "Hello from plugin!")

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """Process context.

        Args:
            context: Current processing context

        Returns:
            Updated context
        """
        # Add a warning to demonstrate plugin is running
        context.add_warning(f"ExamplePlugin: {self.message}")

        # Add some dummy timing
        context.add_timing("example_plugin", 0.1)

        return context
