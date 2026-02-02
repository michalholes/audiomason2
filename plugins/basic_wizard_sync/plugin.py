"""Synchronous Basic Wizard Plugin - configurable workflow version.

Supports YAML-based workflow configuration for:
- Custom step ordering
- Enable/disable steps
- Conditional execution
- Custom prompts and defaults
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from audiomason.core import ProcessingContext, State
from audiomason.core.errors import AudioMasonError

# Import workflow reader
try:
    from .workflow_reader import WorkflowConfig, WorkflowStep
except ImportError:
    try:
        from basic_wizard_sync.workflow_reader import WorkflowConfig, WorkflowStep
    except ImportError:
        from workflow_reader import WorkflowConfig, WorkflowStep  # type: ignore[import-not-found]


class WizardError(AudioMasonError):
    """Wizard execution error."""

    pass


class BasicWizardSync:
    """Synchronous basic wizard with configurable workflow."""

    def __init__(self, config: dict | None = None, workflow_file: Path | None = None) -> None:
        """Initialize wizard.

        Args:
            config: Plugin configuration
            workflow_file: Path to workflow YAML file
        """
        self.config = config or {}
        self.verbosity = self.config.get("verbosity", 1)

        # Load workflow
        if workflow_file and workflow_file.exists():
            self.workflow = WorkflowConfig(workflow_file)
            self._log_debug(f"Loaded workflow: {self.workflow.name}")
        else:
            raise WizardError(f"Workflow file not found: {workflow_file}")

        # Paths
        inbox = self.config.get("inbox_dir", "~/Audiobooks/inbox")
        stage = self.config.get("stage_dir", "/tmp/audiomason/stage")
        output = self.config.get("output_dir", "~/Audiobooks/output")

        self.inbox_dir = Path(inbox).expanduser().resolve()
        self.stage_dir = Path(stage).expanduser().resolve()
        self.output_dir = Path(output).expanduser().resolve()

        # Plugin instances (loaded lazily)
        self._plugins: dict[str, Any] = {}

        # Answers from preflight
        self.answers: dict[str, Any] = {}

        # Context for condition evaluation
        self.eval_context = {"answers": self.answers, "config": self.config}

    def _log_debug(self, msg: str) -> None:
        """Log debug message (verbosity >= 3)."""
        if self.verbosity >= 3 and self.workflow.should_show_messages(
            self.verbosity, "config_values"
        ):
            print(f"[DEBUG] {msg}")

    def _log_verbose(self, msg: str) -> None:
        """Log verbose message (verbosity >= 2)."""
        if self.verbosity >= 2 and self.workflow.should_show_messages(
            self.verbosity, "plugin_calls"
        ):
            print(f"[VERBOSE] {msg}")

    def _log_info(self, msg: str) -> None:
        """Log info message (verbosity >= 1)."""
        if self.verbosity >= 1 and self.workflow.should_show_messages(self.verbosity, "progress"):
            print(msg)

    def _log_workflow(self, msg: str) -> None:
        """Log workflow step (verbosity >= 1)."""
        if self.verbosity >= 1 and self.workflow.should_show_messages(
            self.verbosity, "workflow_steps"
        ):
            print(msg)

    def _log_error(self, msg: str) -> None:
        """Log error message (always shown)."""
        if self.workflow.should_show_messages(self.verbosity, "errors"):
            print(f"[ERROR] {msg}")

    def _get_plugin(self, plugin_name: str) -> Any:
        """Get or load plugin instance.

        Args:
            plugin_name: Plugin name (e.g. 'file_io_sync')

        Returns:
            Plugin instance
        """
        if plugin_name in self._plugins:
            return self._plugins[plugin_name]

        # Load plugin
        plugin_map = {
            "file_io_sync": ("plugins.file_io_sync.plugin", "FileIOSync"),
            "audio_processor_sync": ("plugins.audio_processor_sync.plugin", "AudioProcessorSync"),
            "id3_tagger_sync": ("plugins.id3_tagger_sync.plugin", "ID3TaggerSync"),
            "cover_handler_sync": ("plugins.cover_handler_sync.plugin", "CoverHandlerSync"),
            "metadata_sync": ("plugins.metadata_sync.plugin", "MetadataSync"),
        }

        if plugin_name not in plugin_map:
            raise WizardError(f"Unknown plugin: {plugin_name}")

        module_path, class_name = plugin_map[plugin_name]

        try:
            # Import plugin
            parts = module_path.split(".")
            module_name = ".".join(parts[:-1])
            file_name = parts[-1]

            if module_name:
                exec(f"from {module_name}.{file_name} import {class_name}")
            else:
                exec(f"from {file_name} import {class_name}")

            plugin_class = locals()[class_name]

            # Create instance with config
            plugin_config = self.config.copy()
            plugin_config["verbosity"] = self.verbosity

            plugin_instance = plugin_class(plugin_config)
            self._plugins[plugin_name] = plugin_instance

            self._log_debug(f"Loaded plugin: {plugin_name}")
            return plugin_instance

        except Exception as e:
            raise WizardError(f"Failed to load plugin {plugin_name}: {e}") from e

    def _prompt(self, question: str, default: str = "") -> str:
        """Prompt user for input.

        Args:
            question: Question to ask
            default: Default value

        Returns:
            User input or default
        """
        if self.verbosity >= 1 and self.workflow.should_show_messages(self.verbosity, "prompts"):
            prompt_text = f"{question} [{default}]: " if default else f"{question}: "

            try:
                answer = input(prompt_text).strip()
                return answer if answer else default
            except (EOFError, KeyboardInterrupt):
                print()
                raise WizardError("User interrupted") from None
        else:
            # Non-interactive mode - use default
            return default

    def _prompt_yes_no(self, question: str, default_no: bool = True) -> bool:
        """Prompt user for yes/no answer.

        Args:
            question: Question to ask
            default_no: If True, default is 'no', else 'yes'

        Returns:
            True for yes, False for no
        """
        if self.verbosity >= 1 and self.workflow.should_show_messages(self.verbosity, "prompts"):
            prompt_text = f"{question} (y/N): " if default_no else f"{question} (Y/n): "

            try:
                answer = input(prompt_text).strip().lower()

                if not answer:
                    return not default_no

                return answer in ["y", "yes"]

            except (EOFError, KeyboardInterrupt):
                print()
                raise WizardError("User interrupted") from None
        else:
            # Non-interactive mode - use default
            return not default_no

    def _execute_preflight_step(self, step: WorkflowStep, source_name: str) -> Any:
        """Execute single preflight step.

        Args:
            step: Workflow step to execute
            source_name: Name of source (for hints)

        Returns:
            Step result
        """
        # Check if should skip (already set in config/CLI)
        if step.skip_if_set and step.id in self.config:
            value = self.config[step.id]
            self._log_debug(f"Skipping {step.id} (set in config: {value})")
            return value

        # Execute based on step type
        if step.type == "yes_no":
            default_no = step.default != "yes"
            return self._prompt_yes_no(step.prompt, default_no)

        elif step.type == "input":
            # Extract hint if configured
            hint = step.default or ""

            if step.hint_from == "source_name" and step.hint_pattern:
                hint = self.workflow.extract_hint(step, source_name)

            return self._prompt(step.prompt, hint)

        elif step.type == "menu":
            # Menu handled separately
            return None

        return None

    def _execute_processing_step(
        self, step: WorkflowStep, context: ProcessingContext
    ) -> ProcessingContext:
        """Execute single processing step.

        Args:
            step: Workflow step to execute
            context: Processing context

        Returns:
            Updated context
        """
        # Check condition
        if not self.workflow.evaluate_condition(step.condition, self.eval_context):
            self._log_verbose(f"Skipping {step.id} (condition not met)")
            return context

        # Get plugin and method
        if step.plugin is None:
            raise WizardError(f"Step {step.id} has no plugin specified")
        if step.method is None:
            raise WizardError(f"Step {step.id} has no method specified")
        
        plugin = self._get_plugin(step.plugin)
        method = getattr(plugin, step.method, None)

        if not method:
            raise WizardError(f"Method {step.method} not found in {step.plugin}")

        # Execute
        self._log_workflow(f"=== {step.description} ===")

        try:
            result = method(context)
            return result if result else context
        except Exception as e:
            raise WizardError(f"Step {step.id} failed: {e}") from e

    def run_workflow(self, source_path: Path | None = None) -> ProcessingContext | None:
        """Run complete wizard workflow.

        Args:
            source_path: Optional specific source to process

        Returns:
            Processing context with results, or None if interrupted
        """
        self._log_debug("=== Starting Workflow ===")
        self._log_info(f"Workflow: {self.workflow.name}")

        # Get file_io plugin for source detection
        file_io = self._get_plugin("file_io_sync")

        # Detect sources
        self._log_verbose("Detecting sources...")
        all_sources = file_io.detect_sources(source_path)

        if not all_sources:
            raise WizardError("No sources found in inbox")

        # Group sources by author
        authors: dict[str, list] = {}
        standalone_sources = []

        for source in all_sources:
            if "/" in source.name:
                # autor/kniha structure
                author = source.name.split("/")[0]
                if author not in authors:
                    authors[author] = []
                authors[author].append(source)
            else:
                # Standalone source (archive, single directory)
                standalone_sources.append(source)

        # First step: Select author or standalone source
        if self.workflow.should_show_messages(self.verbosity, "prompts"):
            self._log_info("[inbox] sources:")

            menu_items = []
            idx = 1

            # Show authors first
            for author in sorted(authors.keys()):
                count = len(authors[author])
                self._log_info(f"  {idx}) {author}/ ({count} books)")
                menu_items.append(("author", author))
                idx += 1

            # Show standalone sources
            for source in standalone_sources:
                self._log_info(f"  {idx}) {source.name}")
                menu_items.append(("source", source))
                idx += 1

            try:
                answer = self._prompt("Choose number, or 'a' for all", "1")
                answer = answer.strip().lower()

                if answer == "a":
                    # Process all
                    selected_sources = all_sources
                else:
                    num = int(answer)
                    if 1 <= num <= len(menu_items):
                        item_type, item = menu_items[num - 1]

                        if item_type == "author":
                            # Second step: Select book(s) from author
                            books = authors[item]

                            if len(books) == 1:
                                # Only one book, select it
                                selected_sources = books
                            else:
                                # Multiple books, show menu
                                self._log_info(f"\n[{item}] books:")
                                for book_idx, book in enumerate(books, 1):
                                    book_title = book.name.split("/")[1]
                                    self._log_info(f"  {book_idx}) {book_title}")

                                book_answer = self._prompt(
                                    "Choose book number, or 'a' for all", "1"
                                )
                                book_answer = book_answer.strip().lower()

                                if book_answer == "a":
                                    selected_sources = books
                                else:
                                    book_num = int(book_answer)
                                    if 1 <= book_num <= len(books):
                                        selected_sources = [books[book_num - 1]]
                                    else:
                                        raise WizardError("Invalid book number")
                        else:
                            # Standalone source
                            selected_sources = [item]
                    else:
                        raise WizardError("Invalid selection")
            except (ValueError, IndexError):
                raise WizardError("Invalid input") from None
            except (EOFError, KeyboardInterrupt):
                self._log_info("\n\n[Interrupted by user]")
                return None
        else:
            # Non-interactive - use first source
            selected_sources = [all_sources[0]]

        # Process each selected source
        context = None
        for idx, source_info in enumerate(selected_sources, 1):
            self._log_info(f"\n[source] {idx}/{len(selected_sources)}: {source_info.name}")

            try:
                # Execute preflight steps
                self._log_workflow("\n=== Preflight Questions ===")

                for step in self.workflow.get_enabled_preflight_steps():
                    if step.type != "menu":  # Menu already handled
                        result = self._execute_preflight_step(step, source_info.name)
                        if result is not None:
                            self.answers[step.id] = result
                            self._log_debug(f"{step.id} = {result}")

                # Update eval context
                self.eval_context["answers"] = self.answers

                # Create processing context
                context = ProcessingContext(
                    id=source_info.name, source=source_info.path, state=State.INIT
                )

                # Set metadata from answers
                if "author" in self.answers:
                    context.author = self.answers["author"]
                if "title" in self.answers:
                    context.title = self.answers["title"]

                # Execute processing steps
                self._log_workflow("\n=== Processing ===")
                context.state = State.PROCESSING

                for step in self.workflow.get_enabled_processing_steps():
                    context = self._execute_processing_step(step, context)

                # Mark complete
                context.state = State.DONE
                self._log_info(f"\n✓ Source processed: {source_info.name}")

            except KeyboardInterrupt:
                self._log_info("\n\n[Interrupted by user]")
                return context
            except WizardError as e:
                if "User interrupted" in str(e):
                    self._log_info("\n\n[Interrupted by user]")
                    return context
                self._log_error(f"Failed to process {source_info.name}: {e}")
                if self.verbosity >= 3:
                    import traceback

                    traceback.print_exc()
                continue
            except Exception as e:
                self._log_error(f"Failed to process {source_info.name}: {e}")
                if self.verbosity >= 3:
                    import traceback

                    traceback.print_exc()
                continue

        self._log_info("\n=== Workflow Complete ===")
        return context

    def process(self, context: ProcessingContext) -> ProcessingContext:
        """Main processing method (IProcessor interface).

        Args:
            context: Processing context

        Returns:
            Updated context
        """
        result = self.run_workflow()
        if result is None:
            raise WizardError("Workflow returned None")
        return result
