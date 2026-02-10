"""CLI plugin - Enhanced command-line interface with preflight and verbosity.

Features:
- Preflight detection (auto-guess metadata)
- Smart batch grouping
- 4 verbosity modes (quiet/normal/verbose/debug)
- Progress display
- User-friendly prompts
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any, cast

from audiomason.core import (
    ConfigResolver,
    CoverChoice,
    PluginLoader,
    PreflightResult,
    ProcessingContext,
    State,
    detect_file_groups,
    detect_format,
    find_file_cover,
    guess_author_from_path,
    guess_title_from_path,
    guess_year_from_path,
)
from audiomason.core.config_service import ConfigService
from audiomason.core.jobs.model import JobState, JobType
from audiomason.core.logging import apply_logging_policy, get_logger
from audiomason.core.orchestration import Orchestrator
from audiomason.core.orchestration_models import ProcessRequest
from audiomason.core.plugin_registry import PluginRegistry

log = get_logger(__name__)


class VerbosityLevel:
    """Verbosity levels."""

    QUIET = 0  # Errors only
    NORMAL = 1  # Progress + warnings + errors
    VERBOSE = 2  # Detailed info
    DEBUG = 3  # Everything


class CLIPlugin:
    """Enhanced CLI plugin."""

    def __init__(self, config: dict | None = None) -> None:
        """Initialize CLI plugin.

        Args:
            config: Plugin configuration
        """
        self.config = config or {}
        self.verbosity = VerbosityLevel.NORMAL

    def _parse_cli_args(self, *, emit_debug: bool = True) -> dict[str, Any]:
        """Parse all CLI arguments into a dictionary for ConfigResolver.

        Returns:
            Dictionary of CLI arguments with nested structure for dotted keys
        """
        cli_args: dict[str, Any] = {}

        def _ensure_dict(root: dict[str, Any], key: str) -> dict[str, Any]:
            val = root.get(key)
            if isinstance(val, dict):
                return cast(dict[str, Any], val)
            new: dict[str, Any] = {}
            root[key] = new
            return new

        # Use original argv (before verbosity extraction)
        args = getattr(self, "_original_argv", sys.argv)[1:]  # Skip program name
        i = 0

        while i < len(args):
            arg = args[i]

            # Verbosity flags
            if arg in ("-q", "--quiet"):
                _ensure_dict(cli_args, "logging")["level"] = "quiet"
            elif arg in ("-v", "--verbose"):
                _ensure_dict(cli_args, "logging")["level"] = "verbose"
            elif arg in ("-d", "--debug"):
                _ensure_dict(cli_args, "logging")["level"] = "debug"

            # Port flag - nested under 'web'
            elif arg == "--port" and i + 1 < len(args):
                _ensure_dict(cli_args, "web")["port"] = int(args[i + 1])
                i += 1  # Skip next arg

            # Bitrate flag - nested under 'audio'
            elif arg == "--bitrate" and i + 1 < len(args):
                _ensure_dict(cli_args, "audio")["bitrate"] = args[i + 1]
                i += 1

            # Output directory
            elif arg == "--output" and i + 1 < len(args):
                cli_args["output_dir"] = args[i + 1]
                i += 1

            # Pipeline
            elif arg == "--pipeline" and i + 1 < len(args):
                cli_args["pipeline"] = args[i + 1]
                i += 1

            # Loudnorm flag - nested under 'audio'
            elif arg == "--loudnorm":
                _ensure_dict(cli_args, "audio")["loudnorm"] = True
            elif arg == "--no-loudnorm":
                _ensure_dict(cli_args, "audio")["loudnorm"] = False

            # Split chapters - nested under 'audio'
            elif arg == "--split-chapters":
                _ensure_dict(cli_args, "audio")["split_chapters"] = True
            elif arg == "--no-split-chapters":
                _ensure_dict(cli_args, "audio")["split_chapters"] = False

            i += 1

        if emit_debug:
            self._debug(f"Parsed CLI args: {cli_args}")
        return cli_args

    def _extract_verbosity_from_argv(self) -> None:
        """Extract verbosity flags from sys.argv and remove them.

        This allows verbosity flags to be in ANY position:
        - audiomason -d tui
        - audiomason tui -d
        - audiomason -v wizard advanced
        """
        # Check all arguments for verbosity flags
        args_to_remove = []

        for i, arg in enumerate(sys.argv):
            if arg in ("-q", "--quiet"):
                self.verbosity = VerbosityLevel.QUIET
                args_to_remove.append(i)
            elif arg in ("-v", "--verbose"):
                self.verbosity = VerbosityLevel.VERBOSE
                args_to_remove.append(i)
            elif arg in ("-d", "--debug"):
                self.verbosity = VerbosityLevel.DEBUG
                args_to_remove.append(i)

        # Remove verbosity flags from sys.argv (in reverse order to preserve indices)
        for i in reversed(args_to_remove):
            sys.argv.pop(i)

        self._debug(f"Verbosity level set to: {self.verbosity}")

    async def run(self) -> None:
        """Run CLI - main entry point."""
        if len(sys.argv) < 2:
            self._print_usage()
            return

        # Store original argv before modification
        self._original_argv = sys.argv.copy()

        # Extract verbosity flags from ANY position in argv
        self._extract_verbosity_from_argv()

        # Resolve logging policy and apply it to the core logger (global).
        # This must come from ConfigResolver.resolve_logging_policy() and must
        # not be derived directly from self.verbosity.
        cli_args = self._parse_cli_args(emit_debug=False)
        resolver = ConfigResolver(cli_args=cli_args)
        policy = resolver.resolve_logging_policy()
        apply_logging_policy(policy)

        # Now that core logging is configured, emit debug-only diagnostics.
        self._debug(f"Parsed CLI args: {cli_args}")

        command = sys.argv[1]

        # Handle --help and -h flags
        if command in ("--help", "-h"):
            self._print_usage()
            return

        if command == "process":
            await self._process_command(sys.argv[2:])
        elif command == "wizard":
            await self._wizard_command(sys.argv[2:])
        elif command == "tui":
            await self._tui_command()
        elif command == "version":
            self._version_command()
        elif command == "help":
            self._print_usage()
        elif command == "web":
            await self._web_command(sys.argv[2:])
        elif command == "daemon":
            await self._daemon_command()
        elif command == "checkpoints":
            await self._checkpoints_command(sys.argv[2:])
        else:
            self._error(f"Unknown command: {command}")
            self._print_usage()

    def _print_usage(self) -> None:
        """Print usage information."""
        print("AudioMason v2.0.0-alpha")
        print()
        print("Usage:")
        print("  audiomason process <file(s)>   Process audiobook file(s)")
        print("  audiomason wizard [name]       Run wizard (interactive)")
        print("  audiomason tui                 Terminal UI (ncurses)")
        print("  audiomason web [--port PORT]   Start web server")
        print("  audiomason daemon              Start daemon mode")
        print("  audiomason checkpoints         Manage checkpoints")
        print("  audiomason version             Show version")
        print("  audiomason help                Show this help")
        print()
        print("Options:")
        print("  --author TEXT                  Book author")
        print("  --title TEXT                   Book title")
        print("  --year INT                     Publication year")
        print("  --bitrate TEXT                 Audio bitrate (default: 128k)")
        print("  --loudnorm                     Enable loudness normalization")
        print("  --split-chapters               Split M4A by chapters")
        print("  --cover [embedded|file|url|skip]  Cover source")
        print("  --cover-url URL                Cover URL (if --cover url)")
        print()
        print("Verbosity:")
        print("  -q, --quiet                    Quiet mode (errors only)")
        print("  -v, --verbose                  Verbose mode (detailed info)")
        print("  -d, --debug                    Debug mode (everything)")
        print()
        print("Examples:")
        print("  audiomason tui                 Launch terminal interface")
        print("  audiomason wizard              List available wizards")
        print("  audiomason wizard quick_import Run quick import wizard")
        print("  audiomason process book.m4a")
        print('  audiomason process book.m4a --author "George Orwell" --title "1984"')
        print("  audiomason web --port 8080")
        print("  audiomason process *.m4a --bitrate 320k --loudnorm -v")

    def _version_command(self) -> None:
        """Print version."""
        print("AudioMason v2.0.0-alpha")

    async def _process_command(self, args: list[str]) -> None:
        """Process command.

        Args:
            args: Command arguments
        """
        # Parse arguments
        files, cli_args = self._parse_args(args)
        self.cli_args = cli_args  # Store for processing phase

        if not files:
            self._error("No input file(s) specified")
            self._print_usage()
            return

        # Verbosity is already set globally in run()

        self._info(f"[AUDIO] AudioMason v2 - Processing {len(files)} file(s)")
        self._info("")

        # ===========================================
        #  PHASE 0: PREFLIGHT
        # ===========================================

        self._verbose("Phase 0: Preflight detection...")
        preflight_results = await self._preflight_phase(files)

        # ===========================================
        #  PHASE 1: USER INPUT
        # ===========================================

        self._verbose("Phase 1: Collecting metadata...")
        contexts = await self._input_phase(files, preflight_results, cli_args)

        if not contexts:
            return

        # ===========================================
        #  PHASE 2: PROCESSING
        # ===========================================

        self._info("Phase 2: Processing...")
        self._info("")

        # Phase 2 is executed via the core orchestrator.
        await self._processing_phase_orchestrated(contexts)

    async def _processing_phase_orchestrated(self, contexts: list[ProcessingContext]) -> None:
        """Process via the core orchestrator (Phase 2).

        Args:
            contexts: Processing contexts
        """
        self._verbose("Loading plugins...")
        plugins_dir = Path(__file__).parent.parent
        cfg = ConfigService()
        reg = PluginRegistry(cfg)
        loader = PluginLoader(builtin_plugins_dir=plugins_dir, registry=reg)

        required_plugins = ["audio_processor", "file_io", "id3_tagger", "cover_handler"]
        for plugin_name in required_plugins:
            plugin_dir = plugins_dir / plugin_name
            if not plugin_dir.exists():
                continue
            try:
                loader.load_plugin(plugin_dir, validate=False)
                self._debug(f"  loaded {plugin_name}")
            except Exception as e:  # pragma: no cover
                self._verbose(f"  {plugin_name}: {e}")

        pipeline_name = self.cli_args.get("pipeline", "standard")
        pipeline_path = Path(__file__).parent.parent.parent / "pipelines" / f"{pipeline_name}.yaml"
        if not pipeline_path.exists():
            self._error(f"Pipeline not found: {pipeline_path}")
            return

        orch = Orchestrator()
        job_id = orch.start_process(
            ProcessRequest(contexts=contexts, pipeline_path=pipeline_path, plugin_loader=loader)
        )

        offset = 0
        while True:
            job = orch.get_job(job_id)
            chunk, offset = orch.read_log(job_id, offset=offset)
            if chunk:
                for line in chunk.splitlines():
                    self._info(line)

            if job.state in (JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED):
                break

            await asyncio.sleep(0.2)

        if job.state == JobState.FAILED and job.error:
            self._error(job.error)

    async def _preflight_phase(self, files: list[Path]) -> dict[Path, PreflightResult]:
        """Run preflight detection.

        Args:
            files: Input files

        Returns:
            Dict of file -> PreflightResult
        """
        results = {}

        for file in files:
            result = PreflightResult()

            # Detect format
            fmt = detect_format(file)
            result.is_m4a = fmt == "m4a"
            result.is_opus = fmt == "opus"
            result.is_mp3 = fmt == "mp3"

            # Guess metadata
            result.guessed_author = guess_author_from_path(file)
            result.guessed_title = guess_title_from_path(file)
            result.guessed_year = guess_year_from_path(file)

            # Check for file cover
            cover = find_file_cover(file.parent)
            result.has_file_cover = cover is not None
            result.file_cover_path = cover

            # File info
            result.file_size_bytes = file.stat().st_size

            results[file] = result

            self._debug(f"  {file.name}:")
            self._debug(f"    Format: {fmt}")
            self._debug(f"    Guessed author: {result.guessed_author}")
            self._debug(f"    Guessed title: {result.guessed_title}")

        return results

    async def _input_phase(
        self,
        files: list[Path],
        preflight_results: dict[Path, PreflightResult],
        cli_args: dict[str, Any],
    ) -> list[ProcessingContext]:
        """Collect user input.

        Args:
            files: Input files
            preflight_results: Preflight results
            cli_args: CLI arguments

        Returns:
            List of contexts with metadata
        """
        contexts = []

        # Smart grouping by author
        groups = detect_file_groups(files)

        self._verbose(f"Detected {len(groups)} author group(s)")

        # Ask for author per group
        author_map = {}

        for author_guess, group_files in groups.items():
            # Check if author provided via CLI
            if cli_args.get("author"):
                author = cli_args["author"]
            else:
                # Prompt for author
                default = author_guess if author_guess != "unknown" else None
                prompt_text = f"\U0001f4da Author for {len(group_files)} file(s)"
                if default:
                    prompt_text += f" [{default}]"
                prompt_text += ": "

                try:
                    author = input(prompt_text).strip()
                    if not author and default:
                        author = default
                except (KeyboardInterrupt, EOFError):
                    self._error("\nCancelled")
                    return []

            # Map all files in group to this author
            for file in group_files:
                author_map[file] = author

        # Create contexts
        for file in files:
            preflight = preflight_results[file]

            # Create context
            ctx = ProcessingContext(
                id=str(uuid.uuid4()),
                source=file,
                state=State.INIT,
                preflight=preflight,
            )

            # Author
            ctx.author = author_map.get(file, "Unknown")

            # Title
            if cli_args.get("title"):
                ctx.title = cli_args["title"]
            else:
                default = preflight.guessed_title
                prompt_text = f"\U0001f4d6 Title for {file.name}"
                if default:
                    prompt_text += f" [{default}]"
                prompt_text += ": "

                try:
                    title = input(prompt_text).strip()
                    if not title and default:
                        title = default
                    ctx.title = title if title else file.stem
                except (KeyboardInterrupt, EOFError):
                    self._error("\nCancelled")
                    return []

            # Year
            if cli_args.get("year"):
                ctx.year = cli_args["year"]
            elif preflight.guessed_year:
                ctx.year = preflight.guessed_year

            # Cover choice
            if cli_args.get("cover"):
                cover_str = cli_args["cover"].lower()
                ctx.cover_choice = {
                    "embedded": CoverChoice.EMBEDDED,
                    "file": CoverChoice.FILE,
                    "url": CoverChoice.URL,
                    "skip": CoverChoice.SKIP,
                }.get(cover_str, CoverChoice.SKIP)

                if ctx.cover_choice == CoverChoice.URL and cli_args.get("cover_url"):
                    ctx.cover_url = cli_args["cover_url"]

            # Processing options
            ctx.bitrate = cli_args.get("bitrate", "128k")  # type: ignore[attr-defined]  # type: ignore[attr-defined]
            ctx.loudnorm = cli_args.get("loudnorm", False)
            ctx.split_chapters = cli_args.get("split_chapters", False)

            contexts.append(ctx)

        self._info("")
        self._verbose(f"Collected metadata for {len(contexts)} file(s)")
        self._info("")

        return contexts

    def _parse_args(self, args: list[str]) -> tuple[list[Path], dict[str, Any]]:
        """Parse command-line arguments.

        Args:
            args: Argument list

        Returns:
            (files, options) tuple
        """
        files = []
        options: dict[str, Any] = {}
        i = 0

        while i < len(args):
            arg = args[i]

            if arg.startswith("--"):
                key = arg[2:]

                # Boolean flags
                if key in [
                    "loudnorm",
                    "split-chapters",
                    "split_chapters",
                    "quiet",
                    "verbose",
                    "debug",
                ]:
                    options[key.replace("-", "_")] = True
                    i += 1
                # Value options
                elif i + 1 < len(args) and not args[i + 1].startswith("-"):
                    value = args[i + 1]
                    options[key.replace("-", "_")] = value
                    i += 2
                else:
                    i += 1

            elif arg.startswith("-"):
                # Short flags
                if arg == "-q":
                    options["quiet"] = True
                elif arg == "-v":
                    options["verbose"] = True
                elif arg == "-d":
                    options["debug"] = True
                i += 1

            else:
                # File argument - expand wildcards
                from glob import glob

                matches = glob(arg)
                if matches:
                    files.extend([Path(f) for f in matches if Path(f).is_file()])
                else:
                    # Not a wildcard, just a file
                    file = Path(arg)
                    if file.exists():
                        files.append(file)
                i += 1

        return files, options

    # Logging methods
    def _info(self, msg: str) -> None:
        """Log info message."""
        log.info(msg)

    def _verbose(self, msg: str) -> None:
        """Log verbose message."""
        if self.verbosity >= VerbosityLevel.VERBOSE:
            log.info(msg)

    def _debug(self, msg: str) -> None:
        """Log debug message."""
        if self.verbosity >= VerbosityLevel.DEBUG:
            log.debug(msg)

    def _error(self, msg: str) -> None:
        """Log error message."""
        log.error(msg)

    def _configure_quiet_web_console(self) -> None:
        """Configure logging so quiet web mode prints only the required 2 lines.

        This is intentionally scoped to the current process invocation.
        """
        import logging

        # Disable everything below ERROR globally.
        logging.disable(logging.ERROR - 1)

        # Uvicorn uses these loggers for startup/shutdown and access logs.
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            logger = logging.getLogger(name)
            logger.handlers.clear()
            logger.propagate = False
            logger.setLevel(logging.ERROR)

    async def _web_command(self, args: list[str]) -> None:
        """Start web server.

        Args:
            args: Command arguments
        """
        if self.verbosity >= VerbosityLevel.DEBUG:
            self._debug(f"Starting web server with verbosity: {self.verbosity}")

        # Parse CLI arguments
        cli_args = self._parse_cli_args()

        if self.verbosity >= VerbosityLevel.DEBUG:
            log.debug(f"Parsed CLI args: {cli_args}")

        # Create ConfigResolver with CLI args
        config_resolver = ConfigResolver(cli_args=cli_args)

        # Resolve web server port
        try:
            port, source = config_resolver.resolve("web.port")
            if self.verbosity >= VerbosityLevel.DEBUG:
                log.debug(f"Resolved port {port} from {source}")
            self._verbose(f"Using port {port} (source: {source})")
        except Exception as e:
            port = 8080
            if self.verbosity >= VerbosityLevel.DEBUG:
                log.debug(f"Failed to resolve web.port: {e}, using default 8080")
            self._debug("Using default port 8080")

        if self.verbosity <= VerbosityLevel.QUIET:
            self._configure_quiet_web_console()
            print(f"Starting web server on port {port}...", flush=True)
        else:
            self._info(f"\U0001f310 Starting web server on port {port}...")

        # Load web server plugin
        plugins_dir = Path(__file__).parent.parent
        cfg = ConfigService()
        reg = PluginRegistry(cfg)
        loader = PluginLoader(builtin_plugins_dir=plugins_dir, registry=reg)

        if self.verbosity >= VerbosityLevel.DEBUG:
            log.debug(f"Plugins directory: {plugins_dir}")
            log.debug("Loading all plugins...")

        # Load all plugins first (so web UI can list them)
        plugin_dirs = [
            d for d in plugins_dir.iterdir() if d.is_dir() and (d / "plugin.yaml").exists()
        ]

        if self.verbosity >= VerbosityLevel.DEBUG:
            log.debug(f"Found {len(plugin_dirs)} plugin directories")

        for plugin_dir in plugin_dirs:
            try:
                if self.verbosity >= VerbosityLevel.DEBUG:
                    log.debug(f"Loading: {plugin_dir.name}...")
                loader.load_plugin(plugin_dir, validate=False)
                if self.verbosity >= VerbosityLevel.DEBUG:
                    log.debug("OK Loaded")
            except Exception as e:
                if self.verbosity >= VerbosityLevel.DEBUG:
                    log.debug(f"X Failed: {e}")

        if self.verbosity >= VerbosityLevel.DEBUG:
            loaded = loader.list_plugins()
            log.debug(f"Successfully loaded {len(loaded)} plugins: {loaded}")

        # Get web_server plugin
        web_plugin = loader.get_plugin("web_interface")
        # Backward-compatibility fallback (older name)
        if not web_plugin:
            web_plugin = loader.get_plugin("web_server")
        if not web_plugin:
            self._error("X Web server plugin not found")
            return

        exit_code = 0
        reason = "normal exit"
        try:
            # Pass ConfigResolver and PluginLoader
            web_plugin.config_resolver = config_resolver
            web_plugin.plugin_loader = loader
            web_plugin.verbosity = self.verbosity

            if self.verbosity >= VerbosityLevel.DEBUG:
                log.debug("Web plugin initialized with:")
                log.debug(f"  - config_resolver: {config_resolver is not None}")
                log.debug(f"  - plugin_loader: {loader is not None}")
                log.debug(f"  - verbosity: {self.verbosity}")

            await web_plugin.run()
        except KeyboardInterrupt:
            exit_code = 130
            reason = "interrupted by user"
        except Exception as e:
            exit_code = 1
            reason = f"error: {type(e).__name__}: {e}"
            self._error(f"X Error starting web server: {e}")
            if self.verbosity >= VerbosityLevel.DEBUG:
                import traceback

                log.debug(traceback.format_exc())
        finally:
            if self.verbosity <= VerbosityLevel.QUIET:
                print(f"Finished (reason: {reason})", flush=True)
            else:
                self._info(f"Finished (reason: {reason})")
            raise SystemExit(exit_code)

    async def _daemon_command(self) -> None:
        """Start daemon mode."""
        self._debug(f"Starting daemon mode with verbosity: {self.verbosity}")
        self._info("\U0001f504 Starting daemon mode...")
        self._info("")

        plugins_dir = Path(__file__).parent.parent
        cfg = ConfigService()
        reg = PluginRegistry(cfg)
        loader = PluginLoader(builtin_plugins_dir=plugins_dir, registry=reg)

        daemon_plugin_dir = plugins_dir / "daemon"
        if not daemon_plugin_dir.exists():
            self._error("X Daemon plugin not found")
            return

        try:
            daemon_plugin = loader.load_plugin(daemon_plugin_dir, validate=False)
            # Pass verbosity to daemon
            daemon_plugin.verbosity = self.verbosity
            await daemon_plugin.run()
        except Exception as e:
            self._error(f"X Error starting daemon: {e}")
            if self.verbosity >= VerbosityLevel.DEBUG:
                import traceback

                log.debug(traceback.format_exc())

    async def _checkpoints_command(self, args: list[str]) -> None:
        """Manage checkpoints.

        Args:
            args: Command arguments
        """
        from audiomason.checkpoint import CheckpointManager

        manager = CheckpointManager()

        if not args or args[0] == "list":
            # List checkpoints
            checkpoints = manager.list_checkpoints()

            if not checkpoints:
                print("No checkpoints found")
                return

            print("Available checkpoints:")
            print()
            for cp in checkpoints:
                print(f"  {cp['id']}")
                print(f"    Title: {cp['title']}")
                print(f"    Author: {cp['author']}")
                print(f"    Progress: {cp['progress'] * 100:.0f}%")
                print(f"    State: {cp['state']}")
                print()

        elif args[0] == "cleanup":
            # Cleanup old checkpoints
            days = 7
            if len(args) > 1 and args[1] == "--days":
                days = int(args[2])

            deleted = manager.cleanup_old_checkpoints(days=days)
            print(f"Deleted {deleted} checkpoint(s) older than {days} days")

    async def _wizard_command(self, args: list[str]) -> None:
        """Run wizard command.

        Args:
            args: Command arguments
        """
        import yaml

        from audiomason.core.orchestration import Orchestrator
        from audiomason.core.wizard_service import WizardService

        svc = WizardService()

        # List wizards if no args
        if not args:
            print("\U0001f9d9 Available Wizards:")
            print()
            infos = svc.list_wizards()
            if not infos:
                print("  No wizards found!")
                print(f"  Wizards dir: {svc.wizards_dir}")
                return

            for info in infos:
                try:
                    wizard_def = yaml.safe_load(svc.get_wizard_text(info.name))
                    wizard = wizard_def.get("wizard", {}) if isinstance(wizard_def, dict) else {}
                    name = wizard.get("name", info.name) if isinstance(wizard, dict) else info.name
                    desc = (
                        wizard.get("description", "No description")
                        if isinstance(wizard, dict)
                        else "No description"
                    )
                    print(f"  {info.name}")
                    print(f"    Name: {name}")
                    print(f"    Description: {desc}")
                    print()
                except Exception as e:
                    print(f"  {info.name} (error: {e})")
                    print()

            print("Run a wizard with: audiomason wizard <name>")
            return

        wizard_name = args[0]
        try:
            wizard_yaml = svc.get_wizard_text(wizard_name)
        except Exception as e:
            self._error(str(e))
            infos = svc.list_wizards()
            if infos:
                print(f"Available wizards: {', '.join([i.name for i in infos])}")
            return

        print(f"\U0001f9d9 Running wizard: {wizard_name}")
        print()

        # Create plugin loader
        plugins_dir = Path(__file__).parent.parent
        cfg = ConfigService()
        reg = PluginRegistry(cfg)
        loader = PluginLoader(builtin_plugins_dir=plugins_dir, registry=reg)

        # Collect input payload in UI phase (interactive).
        wizard_obj = yaml.safe_load(wizard_yaml)
        wiz = wizard_obj.get("wizard") if isinstance(wizard_obj, dict) else None
        steps = wiz.get("steps") if isinstance(wiz, dict) else None
        if not isinstance(steps, list):
            self._error("Invalid wizard yaml: missing wizard.steps list")
            return

        payload: dict[str, Any] = {}

        def _ask_choice(prompt: str, choices: list[Any], default: str | None) -> str:
            print(f"\n{prompt}")
            for i, choice in enumerate(choices, 1):
                marker = " (default)" if default and str(choice) == default else ""
                print(f"  {i}. {choice}{marker}")
            while True:
                user_input = input(f"Select [1-{len(choices)}]: ").strip()
                if not user_input and default:
                    return default
                if user_input.isdigit():
                    idx = int(user_input) - 1
                    if 0 <= idx < len(choices):
                        return str(choices[idx])
                print("Invalid choice, try again")

        def _ask_input(prompt: str, required: bool, default: str | None) -> str:
            prompt_text = f"{prompt} [{default}]: " if default else f"{prompt}: "
            while True:
                value = input(prompt_text).strip()
                if not value and default:
                    return default
                if required and not value:
                    print("This field is required")
                    continue
                return value

        def _can_eval_condition(expr: str, data: dict[str, Any]) -> bool | None:
            # Minimal evaluator for "var == 'value'" patterns.
            m = re.match(r"^\s*([A-Za-z0-9_\-]+)\s*==\s*'([^']*)'\s*$", expr)
            if not m:
                return None
            key, val = m.group(1), m.group(2)
            if key not in data:
                return None
            return str(data.get(key)) == val

        def _walk(step_list: list[Any]) -> None:
            for step in step_list:
                if not isinstance(step, dict):
                    continue
                stype = step.get("type")
                sid = step.get("id")
                if isinstance(stype, str) and isinstance(sid, str) and sid and sid not in payload:
                    if stype == "choice":
                        choices = step.get("choices", [])
                        default = step.get("default")
                        if not isinstance(choices, list) or not choices:
                            continue
                        payload[sid] = _ask_choice(
                            str(step.get("prompt", sid)),
                            choices,
                            str(default) if default else None,
                        )
                        continue
                    if stype == "input":
                        required = bool(step.get("required", False))
                        default = step.get("default")
                        payload[sid] = _ask_input(
                            str(step.get("prompt", sid)),
                            required,
                            str(default) if default else None,
                        )
                        continue

                if stype == "condition":
                    cond = step.get("condition")
                    if isinstance(cond, str):
                        res = _can_eval_condition(cond, payload)
                        if res is True and isinstance(step.get("if_true"), list):
                            _walk(step["if_true"])
                            continue
                        if res is False and isinstance(step.get("if_false"), list):
                            _walk(step["if_false"])
                            continue
                    if isinstance(step.get("if_true"), list):
                        _walk(step["if_true"])
                    if isinstance(step.get("if_false"), list):
                        _walk(step["if_false"])

        _walk(steps)

        orch = Orchestrator()
        job = orch.jobs.create_job(
            JobType.WIZARD,
            meta={
                "wizard_id": wizard_name,
                "wizard_path": wizard_name,
                "payload_json": json.dumps(
                    payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
                ),
            },
        )

        try:
            orch.run_job(job.job_id, plugin_loader=loader, verbosity=int(self.verbosity))
        except Exception as e:
            self._error(f"Failed to start wizard job: {e}")
            return

        offset = 0
        while True:
            j = orch.get_job(job.job_id)
            chunk, offset = orch.read_log(job.job_id, offset=offset)
            if chunk:
                for line in chunk.splitlines():
                    self._info(line)

            if j.state in (JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED):
                break

        if j.state == JobState.SUCCEEDED:
            print()
            print("OK Wizard completed successfully!")
        else:
            print()
            self._error(f"Wizard failed (state={j.state}, error={j.error})")

    async def _tui_command(self) -> None:
        """Launch TUI interface."""
        self._debug(f"Launching TUI with verbosity level: {self.verbosity}")

        try:
            # Load TUI plugin
            plugins_dir = Path(__file__).parent.parent
            tui_dir = plugins_dir / "tui"

            if not tui_dir.exists():
                self._error("TUI plugin not found!")
                print("Install TUI plugin to use this feature.")
                return

            # Import and run
            sys.path.insert(0, str(tui_dir))
            from plugin import TUIPlugin  # type: ignore[import-not-found]

            # Pass verbosity level to TUI
            tui = TUIPlugin(config={"verbosity": self.verbosity})
            await tui.run()

        except ImportError as e:
            self._error(f"Failed to load TUI: {e}")
            print("\nTUI requires the 'curses' module.")
            print("On Windows, install: pip install windows-curses")
        except Exception as e:
            self._error(f"TUI error: {e}")
            import traceback

            if self.verbosity >= VerbosityLevel.DEBUG:
                log.debug(traceback.format_exc())
