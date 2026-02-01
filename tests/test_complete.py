#!/usr/bin/env python3
"""Complete test suite - všetky pluginy."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audiomason.core import PluginLoader


def test_all_plugins():
    """Test that all plugins load correctly."""
    print("=" * 70)
    print(" AudioMason v2 - Complete Plugin Test")
    print("=" * 70)
    print()

    plugins_dir = Path(__file__).parent.parent / "plugins"
    loader = PluginLoader(builtin_plugins_dir=plugins_dir)

    # Expected plugins
    expected = [
        "audio_processor",
        "file_io",
        "cli",
        "text_utils",
        "metadata_googlebooks",
        "metadata_openlibrary",
        "id3_tagger",
        "cover_handler",
        "example_plugin",
    ]

    print(f"📁 Plugin directory: {plugins_dir}")
    print(f"🎯 Expected plugins: {len(expected)}")
    print()

    loaded = []
    failed = []

    for plugin_name in expected:
        plugin_dir = plugins_dir / plugin_name

        if not plugin_dir.exists():
            print(f"❌ {plugin_name:25s} - Directory not found")
            failed.append(plugin_name)
            continue

        try:
            loader.load_plugin(plugin_dir, validate=False)
            print(f"✅ {plugin_name:25s} - Loaded successfully")
            loaded.append(plugin_name)
        except Exception as e:
            print(f"❌ {plugin_name:25s} - Failed: {e}")
            failed.append(plugin_name)

    print()
    print("=" * 70)
    print("📊 RESULTS:")
    print(f"   ✅ Loaded:  {len(loaded)}/{len(expected)}")
    print(f"   ❌ Failed:  {len(failed)}/{len(expected)}")
    print()

    if loaded:
        print("✅ Successfully loaded plugins:")
        for name in loaded:
            print(f"   • {name}")
        print()

    if failed:
        print("❌ Failed plugins:")
        for name in failed:
            print(f"   • {name}")
        print()

    print("=" * 70)

    if len(loaded) == len(expected):
        print("🎉 ALL PLUGINS LOADED SUCCESSFULLY!")
        return True
    else:
        print(f"⚠️  {len(failed)} plugins failed to load")
        return False


def test_plugin_lines():
    """Count lines in each plugin."""
    print()
    print("=" * 70)
    print(" Plugin Code Statistics")
    print("=" * 70)
    print()

    plugins_dir = Path(__file__).parent.parent / "plugins"

    total_lines = 0
    plugins_stats = []

    for plugin_dir in plugins_dir.iterdir():
        if not plugin_dir.is_dir():
            continue

        plugin_py = plugin_dir / "plugin.py"
        if plugin_py.exists():
            lines = len(plugin_py.read_text().splitlines())
            total_lines += lines
            plugins_stats.append((plugin_dir.name, lines))

    # Sort by lines descending
    plugins_stats.sort(key=lambda x: x[1], reverse=True)

    print(f"{'Plugin':<30} {'Lines':>10}")
    print("-" * 42)
    for name, lines in plugins_stats:
        print(f"{name:<30} {lines:>10}")
    print("-" * 42)
    print(f"{'TOTAL':<30} {total_lines:>10}")
    print()


def test_pipelines():
    """Test that pipelines load correctly."""
    print("=" * 70)
    print(" Pipeline Test")
    print("=" * 70)
    print()

    from audiomason.core import PipelineExecutor, PluginLoader

    plugins_dir = Path(__file__).parent.parent / "plugins"
    pipelines_dir = Path(__file__).parent.parent / "pipelines"

    # Load plugins first
    loader = PluginLoader(builtin_plugins_dir=plugins_dir)
    executor = PipelineExecutor(loader)

    pipelines = ["minimal.yaml", "standard.yaml"]

    for pipeline_name in pipelines:
        pipeline_path = pipelines_dir / pipeline_name

        if not pipeline_path.exists():
            print(f"❌ {pipeline_name:20s} - Not found")
            continue

        try:
            pipeline = executor.load_pipeline(pipeline_path)
            print(f"✅ {pipeline_name:20s} - {pipeline.name} ({len(pipeline.steps)} steps)")

            for step in pipeline.steps:
                parallel = " (parallel)" if step.parallel else ""
                print(f"   {step.id:15s} → {step.plugin}{parallel}")

        except Exception as e:
            print(f"❌ {pipeline_name:20s} - Failed: {e}")

    print()


def main():
    """Run all tests."""
    try:
        print()

        # Test 1: Plugin loading
        plugins_ok = test_all_plugins()

        # Test 2: Code stats
        test_plugin_lines()

        # Test 3: Pipelines
        test_pipelines()

        print("=" * 70)
        if plugins_ok:
            print("✅ COMPLETE TEST SUITE PASSED")
        else:
            print("⚠️  SOME TESTS FAILED")
        print("=" * 70)
        print()

        return 0 if plugins_ok else 1

    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
