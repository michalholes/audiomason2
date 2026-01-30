"""CLI plugin - Enhanced command-line interface with preflight and verbosity.

Features:
- Preflight detection (auto-guess metadata)
- Smart batch grouping
- 4 verbosity modes (quiet/normal/verbose/debug)
- Progress display
- User-friendly prompts
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path
from typing import Any

from audiomason.core import (
    ConfigResolver,
    PluginLoader,
    PipelineExecutor,
    ProcessingContext,
    PreflightResult,
    State,
    CoverChoice,
    detect_file_groups,
    guess_author_from_path,
    guess_title_from_path,
    guess_year_from_path,
    detect_format,
    find_file_cover,
)


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

    async def run(self) -> None:
        """Run CLI - main entry point."""
        if len(sys.argv) < 2:
            self._print_usage()
            return

        command = sys.argv[1]

        if command == "process":
            await self._process_command(sys.argv[2:])
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
        print("  audiomason process book.m4a")
        print('  audiomason process book.m4a --author "George Orwell" --title "1984"')
        print("  audiomason web --port 8080")
        print("  audiomason daemon")
        print('  audiomason process book.m4a --author "George Orwell" --title "1984"')
        print("  audiomason process *.m4a --bitrate 320k --loudnorm -v")
        print("  audiomason process book.m4a --cover url --cover-url https://example.com/cover.jpg")

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

        if not files:
            self._error("No input file(s) specified")
            self._print_usage()
            return

        # Set verbosity
        if cli_args.get("quiet"):
            self.verbosity = VerbosityLevel.QUIET
        elif cli_args.get("debug"):
            self.verbosity = VerbosityLevel.DEBUG
        elif cli_args.get("verbose"):
            self.verbosity = VerbosityLevel.VERBOSE

        self._info(f"🎧 AudioMason v2 - Processing {len(files)} file(s)")
        self._info("")

        # ═══════════════════════════════════════════
        #  PHASE 0: PREFLIGHT
        # ═══════════════════════════════════════════

        self._verbose("Phase 0: Preflight detection...")
        preflight_results = await self._preflight_phase(files)

        # ═══════════════════════════════════════════
        #  PHASE 1: USER INPUT
        # ═══════════════════════════════════════════

        self._verbose("Phase 1: Collecting metadata...")
        contexts = await self._input_phase(files, preflight_results, cli_args)

        if not contexts:
            return

        # ═══════════════════════════════════════════
        #  PHASE 2: PROCESSING
        # ═══════════════════════════════════════════

        self._info("Phase 2: Processing...")
        self._info("")

        await self._processing_phase(contexts)

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
                prompt_text = f"📚 Author for {len(group_files)} file(s)"
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
                prompt_text = f"📖 Title for {file.name}"
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
            ctx.bitrate = cli_args.get("bitrate", "128k")
            ctx.loudnorm = cli_args.get("loudnorm", False)
            ctx.split_chapters = cli_args.get("split_chapters", False)

            contexts.append(ctx)

        self._info("")
        self._verbose(f"Collected metadata for {len(contexts)} file(s)")
        self._info("")

        return contexts

    async def _processing_phase(self, contexts: list[ProcessingContext]) -> None:
        """Process all contexts.

        Args:
            contexts: Processing contexts
        """
        # Load plugins
        self._verbose("Loading plugins...")
        plugins_dir = Path(__file__).parent.parent
        loader = PluginLoader(builtin_plugins_dir=plugins_dir)

        # Load required plugins
        required_plugins = ["audio_processor", "file_io", "id3_tagger", "cover_handler"]

        for plugin_name in required_plugins:
            plugin_dir = plugins_dir / plugin_name
            if plugin_dir.exists():
                try:
                    loader.load_plugin(plugin_dir, validate=False)
                    self._debug(f"  ✓ {plugin_name}")
                except Exception as e:
                    self._verbose(f"  ⚠ {plugin_name}: {e}")

        # Load pipeline
        pipeline_name = cli_args.get("pipeline", "standard")
        pipeline_path = Path(__file__).parent.parent.parent / "pipelines" / f"{pipeline_name}.yaml"

        if not pipeline_path.exists():
            self._error(f"Pipeline not found: {pipeline_path}")
            return

        executor = PipelineExecutor(loader)

        # Process each file
        for i, ctx in enumerate(contexts, 1):
            self._info(f"[{i}/{len(contexts)}] Processing: {ctx.source.name}")

            start_time = time.time()
            ctx.start_time = start_time

            try:
                result = await executor.execute_from_yaml(pipeline_path, ctx)

                end_time = time.time()
                result.end_time = end_time
                duration = end_time - start_time

                self._info(f"  ✅ Complete ({duration:.1f}s)")

                if result.output_path:
                    self._info(f"  📁 Output: {result.output_path}")

                # Warnings in verbose mode
                if self.verbosity >= VerbosityLevel.VERBOSE and result.warnings:
                    for warning in result.warnings:
                        self._verbose(f"  ⚠️  {warning}")

            except Exception as e:
                self._error(f"  ❌ Error: {e}")
                if hasattr(e, "suggestion"):
                    self._info(f"  💡 {e.suggestion}")

            self._info("")

    def _parse_args(self, args: list[str]) -> tuple[list[Path], dict[str, Any]]:
        """Parse command-line arguments.

        Args:
            args: Argument list

        Returns:
            (files, options) tuple
        """
        files = []
        options = {}
        i = 0

        while i < len(args):
            arg = args[i]

            if arg.startswith("--"):
                key = arg[2:]

                # Boolean flags
                if key in ["loudnorm", "split-chapters", "split_chapters", "quiet", "verbose", "debug"]:
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
        if self.verbosity >= VerbosityLevel.NORMAL:
            print(msg)

    def _verbose(self, msg: str) -> None:
        """Log verbose message."""
        if self.verbosity >= VerbosityLevel.VERBOSE:
            print(msg)

    def _debug(self, msg: str) -> None:
        """Log debug message."""
        if self.verbosity >= VerbosityLevel.DEBUG:
            print(msg)

    def _error(self, msg: str) -> None:
        """Log error message."""
        # Always shown
        print(msg)

    async def _web_command(self, args: list[str]) -> None:
        """Start web server.

        Args:
            args: Command arguments
        """
        # Parse port
        port = 8080
        for i, arg in enumerate(args):
            if arg == "--port" and i + 1 < len(args):
                port = int(args[i + 1])

        print(f"🌐 Starting web server on port {port}...")
        print()

        # Load web server plugin
        plugins_dir = Path(__file__).parent
        loader = PluginLoader(builtin_plugins_dir=plugins_dir)

        web_plugin_dir = plugins_dir / "web_server"
        if not web_plugin_dir.exists():
            print("❌ Web server plugin not found")
            return

        try:
            web_plugin = loader.load_plugin(web_plugin_dir, validate=False)
            web_plugin.config["port"] = port
            await web_plugin.run()
        except Exception as e:
            print(f"❌ Error starting web server: {e}")

    async def _daemon_command(self) -> None:
        """Start daemon mode."""
        print("🔄 Starting daemon mode...")
        print()

        plugins_dir = Path(__file__).parent
        loader = PluginLoader(builtin_plugins_dir=plugins_dir)

        daemon_plugin_dir = plugins_dir / "daemon"
        if not daemon_plugin_dir.exists():
            print("❌ Daemon plugin not found")
            return

        try:
            daemon_plugin = loader.load_plugin(daemon_plugin_dir, validate=False)
            await daemon_plugin.run()
        except Exception as e:
            print(f"❌ Error starting daemon: {e}")

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
