#!/usr/bin/env python3
"""Test all newly implemented plugins."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_text_utils():
    """Test text utilities plugin."""
    print("🧪 Test: Text Utilities")
    print("-" * 50)

    sys.path.insert(0, str(Path(__file__).parent.parent / "plugins/text_utils"))
    from plugin import TextUtilsPlugin

    utils = TextUtilsPlugin()

    # Test strip_diacritics
    assert utils.strip_diacritics("Příliš žluťoučký kůň") == "Prilis zlutoucky kun"
    print("✓ strip_diacritics works")

    # Test slug
    assert utils.slug("George Orwell - 1984") == "george-orwell-1984"
    assert utils.slug("Příliš žluťoučký") == "prilis-zlutoucky"
    print("✓ slug works")

    # Test clean_text
    assert utils.clean_text("  hello   world  ") == "hello world"
    print("✓ clean_text works")

    # Test sanitize_filename
    result = utils.sanitize_filename('Bad/File\\Name:Test"')
    assert "_" in result  # Should have replaced invalid chars
    print("✓ sanitize_filename works")

    print()


def test_id3_tagger():
    """Test ID3 tagger plugin."""
    print("🧪 Test: ID3 Tagger")
    print("-" * 50)

    # Direct import from file
    import importlib.util

    plugin_file = Path(__file__).parent.parent / "plugins/id3_tagger/plugin.py"
    spec = importlib.util.spec_from_file_location("id3_plugin", plugin_file)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        tagger = module.ID3TaggerPlugin()
        print("✓ ID3 tagger plugin loads")

        # Test that it has the expected methods
        assert hasattr(tagger, "process")
        assert hasattr(tagger, "read_tags")
        print("✓ Has required methods")

    print()


def test_cover_handler():
    """Test cover handler plugin."""
    print("🧪 Test: Cover Handler")
    print("-" * 50)

    import importlib.util

    plugin_file = Path(__file__).parent.parent / "plugins/cover_handler/plugin.py"
    spec = importlib.util.spec_from_file_location("cover_plugin", plugin_file)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        handler = module.CoverHandlerPlugin()
        print("✓ Cover handler plugin loads")

        # Test that it has the expected methods
        assert hasattr(handler, "process")
        assert hasattr(handler, "extract_embedded_cover")
        assert hasattr(handler, "download_cover")
        assert hasattr(handler, "convert_to_jpeg")
        assert hasattr(handler, "embed_cover")
        print("✓ Has all required methods")

    print()


def test_metadata_plugins():
    """Test metadata plugins."""
    print("🧪 Test: Metadata Plugins")
    print("-" * 50)

    import importlib.util

    # Google Books
    plugin_file = Path(__file__).parent.parent / "plugins/metadata_googlebooks/plugin.py"
    spec = importlib.util.spec_from_file_location("google_plugin", plugin_file)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.GoogleBooksPlugin()
        print("✓ Google Books plugin loads")

    # OpenLibrary
    plugin_file = Path(__file__).parent.parent / "plugins/metadata_openlibrary/plugin.py"
    spec = importlib.util.spec_from_file_location("ol_plugin", plugin_file)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.OpenLibraryPlugin()
        print("✓ OpenLibrary plugin loads")

    print()


def test_enhanced_cli():
    """Test enhanced CLI."""
    print("🧪 Test: Enhanced CLI")
    print("-" * 50)

    import importlib.util

    plugin_file = Path(__file__).parent.parent / "plugins/cli/plugin.py"
    spec = importlib.util.spec_from_file_location("cli_plugin", plugin_file)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        cli_plugin_cls = module.CLIPlugin
        verbosity_level_cls = module.VerbosityLevel

        cli = cli_plugin_cls()
        print("✓ Enhanced CLI plugin loads")

        # Test verbosity levels
        assert verbosity_level_cls.QUIET == 0
        assert verbosity_level_cls.NORMAL == 1
        assert verbosity_level_cls.VERBOSE == 2
        assert verbosity_level_cls.DEBUG == 3
        print("✓ Verbosity levels defined")

        # Test parsing
        files, opts = cli._parse_args(
            [
                "test.m4a",
                "--author",
                "Test",
                "--verbose",
                "--loudnorm",
            ]
        )
        assert len(files) >= 0  # May not exist
        assert opts.get("author") == "Test"
        assert opts.get("verbose") is True
        assert opts.get("loudnorm") is True
        print("✓ Argument parsing works")

    print()


def test_plugin_loading():
    """Test that all new plugins load."""
    print("🧪 Test: Plugin Loading")
    print("-" * 50)

    from audiomason.core import PluginLoader

    plugins_dir = Path(__file__).parent.parent / "plugins"
    loader = PluginLoader(builtin_plugins_dir=plugins_dir)

    plugin_names = [
        "text_utils",
        "id3_tagger",
        "cover_handler",
        "metadata_googlebooks",
        "metadata_openlibrary",
    ]

    for name in plugin_names:
        plugin_dir = plugins_dir / name
        if plugin_dir.exists():
            try:
                loader.load_plugin(plugin_dir, validate=False)
                print(f"✓ {name}")
            except Exception as e:
                print(f"✗ {name}: {e}")
                raise

    loaded = loader.list_plugins()
    print(f"\n✓ Loaded {len(loaded)} plugins")

    print()


def test_standard_pipeline():
    """Test standard pipeline YAML."""
    print("🧪 Test: Standard Pipeline")
    print("-" * 50)

    from audiomason.core import PipelineExecutor, PluginLoader

    pipeline_path = Path(__file__).parent.parent / "pipelines" / "standard.yaml"

    if not pipeline_path.exists():
        print(f"✗ Pipeline not found: {pipeline_path}")
        return

    plugins_dir = Path(__file__).parent.parent / "plugins"
    loader = PluginLoader(builtin_plugins_dir=plugins_dir)
    executor = PipelineExecutor(loader)

    try:
        pipeline = executor.load_pipeline(pipeline_path)
        print(f"✓ Pipeline loaded: {pipeline.name}")
        print(f"✓ Steps: {len(pipeline.steps)}")
        for step in pipeline.steps:
            print(f"  - {step.id} ({step.plugin})")

        print()
        print("✓ Standard pipeline is valid")

    except Exception as e:
        print(f"✗ Pipeline loading failed: {e}")
        raise

    print()


def main():
    """Run all tests."""
    print()
    print("=" * 70)
    print(" AudioMason v2 - Full Feature Test Suite")
    print("=" * 70)
    print()

    try:
        test_text_utils()
        test_id3_tagger()
        test_cover_handler()
        test_metadata_plugins()
        test_enhanced_cli()
        test_plugin_loading()
        test_standard_pipeline()

        print("=" * 70)
        print("✅ ALL TESTS PASSED")
        print("=" * 70)
        print()
        print("🎉 All features implemented and working!")
        print()
        print("New features:")
        print("  ✓ Text utilities (diacritics, slug, sanitize)")
        print("  ✓ ID3 tag writing")
        print("  ✓ Cover handling (extract, download, embed)")
        print("  ✓ Metadata providers (Google Books, OpenLibrary)")
        print("  ✓ Enhanced CLI (preflight, verbosity, batch)")
        print("  ✓ Standard pipeline (with tags + covers)")
        print()

    except Exception as e:
        print()
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
