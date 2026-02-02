#!/usr/bin/env python3
"""Run basic wizard sync - simple entry point."""

import argparse
import sys
from pathlib import Path

def _configure_import_paths() -> None:
    # Add src and plugins to path for direct execution from repo root.
    src_path = Path(__file__).parent / "src"
    sys.path.insert(0, str(src_path))

    plugins_path = Path(__file__).parent / "plugins"
    sys.path.insert(0, str(plugins_path))




def main():
    """Run basic wizard."""
    _configure_import_paths()

    from audiomason.core.config import ConfigResolver

    parser = argparse.ArgumentParser(description="AudioMason Basic Wizard")

    # Verbosity
    parser.add_argument("--quiet", action="store_true", help="Minimal output (errors only)")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--debug", action="store_true", help="Debug output (everything)")

    # Config
    parser.add_argument("--config", type=Path, help="Config file path")
    parser.add_argument("--workflow", type=Path, help="Workflow YAML file")
    parser.add_argument("--inbox-dir", type=Path, help="Inbox directory")
    parser.add_argument("--stage-dir", type=Path, help="Stage directory")
    parser.add_argument("--output-dir", type=Path, help="Output directory")

    # Processing options
    parser.add_argument(
        "--clean-inbox", choices=["yes", "no", "ask"], help="Clean inbox after import"
    )
    parser.add_argument(
        "--clean-stage", choices=["yes", "no", "ask"], help="Clean stage after import"
    )
    parser.add_argument("--publish", choices=["yes", "no", "ask"], help="Publish to output")
    parser.add_argument(
        "--wipe-id3", choices=["yes", "no", "ask"], help="Wipe ID3 tags before tagging"
    )

    # Audio options
    parser.add_argument("--bitrate", help="Audio bitrate (e.g. 128k, 192k)")
    parser.add_argument("--loudnorm", action="store_true", help="Enable loudness normalization")
    parser.add_argument("--split-chapters", action="store_true", help="Split by chapters")

    args = parser.parse_args()

    # Determine verbosity level
    verbosity = 1  # default
    if args.quiet:
        verbosity = 0
    elif args.verbose:
        verbosity = 2
    elif args.debug:
        verbosity = 3

    # Build CLI args dict
    cli_args = {"verbosity": verbosity}

    if args.inbox_dir:
        cli_args["inbox_dir"] = str(args.inbox_dir)
    if args.stage_dir:
        cli_args["stage_dir"] = str(args.stage_dir)
    if args.output_dir:
        cli_args["output_dir"] = str(args.output_dir)
    if args.clean_inbox:
        cli_args["clean_inbox"] = args.clean_inbox
    if args.clean_stage:
        cli_args["clean_stage"] = args.clean_stage
    if args.publish:
        cli_args["publish"] = args.publish
    if args.wipe_id3:
        cli_args["wipe_id3"] = args.wipe_id3
    if args.bitrate:
        cli_args["bitrate"] = args.bitrate
    if args.loudnorm:
        cli_args["loudnorm"] = True
    if args.split_chapters:
        cli_args["split_chapters"] = True

    # Workflow file
    workflow_file = args.workflow
    if not workflow_file:
        # Default workflow
        workflow_file = Path(__file__).parent / "workflow_sync" / "workflow_basic.yaml"

    # Create config resolver
    config_resolver = ConfigResolver(cli_args=cli_args, user_config_path=args.config)

    # Resolve all config
    resolved_config = {}
    for key in [
        "inbox_dir",
        "stage_dir",
        "output_dir",
        "verbosity",
        "clean_inbox",
        "clean_stage",
        "publish",
        "wipe_id3",
        "bitrate",
        "loudnorm",
        "split_chapters",
    ]:
        try:
            value, source = config_resolver.resolve(key)
            resolved_config[key] = value
            if verbosity >= 3:
                print(f"[DEBUG] Config: {key} = {value} (from {source})")
        except Exception:
            pass

    # Load wizard plugin
    try:
        from basic_wizard_sync.plugin import BasicWizardSync

        if verbosity >= 2:
            print("[VERBOSE] Loading basic_wizard_sync plugin")

        wizard = BasicWizardSync(resolved_config, workflow_file=workflow_file)

        # Run workflow
        if verbosity >= 1:
            print("audiomason_version=2.0.0-sync")
            print()

        wizard.run_workflow()

    except KeyboardInterrupt:
        print("\n[ERROR] Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Wizard failed: {e}")
        if verbosity >= 3:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
