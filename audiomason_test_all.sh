#!/bin/bash
# AudioMason v2 - Comprehensive Bug Hunting Test Script
# Runs all commands and saves outputs to a single file

OUTPUT_FILE="audiomason_test_results_$(date +%Y%m%d_%H%M%S).txt"

echo "╔═══════════════════════════════════════════════╗" | tee "$OUTPUT_FILE"
echo "║   AudioMason v2 - Bug Hunting Test Report    ║" | tee -a "$OUTPUT_FILE"
echo "║   Date: $(date)                ║" | tee -a "$OUTPUT_FILE"
echo "╚═══════════════════════════════════════════════╝" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

# Helper function to run test
run_test() {
    local test_name="$1"
    local command="$2"
    local description="$3"
    
    echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
    echo "TEST: $test_name" | tee -a "$OUTPUT_FILE"
    echo "CMD:  $command" | tee -a "$OUTPUT_FILE"
    echo "DESC: $description" | tee -a "$OUTPUT_FILE"
    echo "────────────────────────────────────────────────" | tee -a "$OUTPUT_FILE"
    
    # Run command and capture both stdout and stderr
    eval "$command" 2>&1 | tee -a "$OUTPUT_FILE"
    
    local exit_code=$?
    echo "" | tee -a "$OUTPUT_FILE"
    echo "EXIT CODE: $exit_code" | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
}

# System info
echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "SYSTEM INFORMATION" | tee -a "$OUTPUT_FILE"
echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "Hostname: $(hostname)" | tee -a "$OUTPUT_FILE"
echo "User: $(whoami)" | tee -a "$OUTPUT_FILE"
echo "PWD: $(pwd)" | tee -a "$OUTPUT_FILE"
echo "Python: $(python3 --version 2>&1)" | tee -a "$OUTPUT_FILE"
echo "Venv: $VIRTUAL_ENV" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

# ═══════════════════════════════════════════
# SECTION 1: Basic Commands
# ═══════════════════════════════════════════

echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "SECTION 1: BASIC COMMANDS" | tee -a "$OUTPUT_FILE"
echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

run_test "1.1" "audiomason version" "Show version"
run_test "1.2" "audiomason help" "Show help"
run_test "1.3" "audiomason --help" "Show help with --help flag"
run_test "1.4" "audiomason -h" "Show help with -h flag"
run_test "1.5" "audiomason" "No arguments (should show usage)"

# ═══════════════════════════════════════════
# SECTION 2: Wizard Commands
# ═══════════════════════════════════════════

echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "SECTION 2: WIZARD COMMANDS" | tee -a "$OUTPUT_FILE"
echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

run_test "2.1" "audiomason wizard" "List all wizards"
run_test "2.2" "ls -la wizards/" "Check wizard files exist"
run_test "2.3" "cat wizards/quick_import.yaml | head -20" "Show quick_import wizard content"

# ═══════════════════════════════════════════
# SECTION 3: Plugin Commands
# ═══════════════════════════════════════════

echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "SECTION 3: PLUGIN COMMANDS" | tee -a "$OUTPUT_FILE"
echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

run_test "3.1" "timeout 2 audiomason web --port 9999 || true" "Start web server (2s timeout)"
run_test "3.2" "timeout 2 audiomason daemon || true" "Start daemon (2s timeout)"
run_test "3.3" "ls -la plugins/" "List all plugins"
run_test "3.4" "ls -la plugins/web_server/" "Check web_server plugin"
run_test "3.5" "ls -la plugins/daemon/" "Check daemon plugin"
run_test "3.6" "ls -la plugins/tui/" "Check tui plugin"

# ═══════════════════════════════════════════
# SECTION 4: TUI Command
# ═══════════════════════════════════════════

echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "SECTION 4: TUI COMMAND" | tee -a "$OUTPUT_FILE"
echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

run_test "4.1" "timeout 1 audiomason tui || true" "Launch TUI (1s timeout)"
run_test "4.2" "python3 -c 'import curses; print(\"curses available\")'" "Check curses module"

# ═══════════════════════════════════════════
# SECTION 5: Checkpoint Commands
# ═══════════════════════════════════════════

echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "SECTION 5: CHECKPOINT COMMANDS" | tee -a "$OUTPUT_FILE"
echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

run_test "5.1" "audiomason checkpoints" "List checkpoints"
run_test "5.2" "audiomason checkpoints list" "List checkpoints (explicit)"
run_test "5.3" "ls -la ~/.local/share/audiomason/checkpoints/ 2>&1 || echo 'Directory not found'" "Check checkpoint directory"

# ═══════════════════════════════════════════
# SECTION 6: File Structure
# ═══════════════════════════════════════════

echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "SECTION 6: FILE STRUCTURE" | tee -a "$OUTPUT_FILE"
echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

run_test "6.1" "ls -la" "Project root"
run_test "6.2" "ls -la src/audiomason/" "src/audiomason directory"
run_test "6.3" "ls -la plugins/" "plugins directory"
run_test "6.4" "ls -la wizards/" "wizards directory"
run_test "6.5" "ls -la docs/" "docs directory"
run_test "6.6" "cat pyproject.toml" "pyproject.toml content"

# ═══════════════════════════════════════════
# SECTION 7: Python Imports
# ═══════════════════════════════════════════

echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "SECTION 7: PYTHON IMPORTS" | tee -a "$OUTPUT_FILE"
echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

run_test "7.1" "python3 -c 'from audiomason.core import PluginLoader; print(\"PluginLoader OK\")'" "Import PluginLoader"
run_test "7.2" "python3 -c 'from audiomason.wizard_engine import WizardEngine; print(\"WizardEngine OK\")'" "Import WizardEngine"
run_test "7.3" "python3 -c 'from audiomason.core import ProcessingContext; print(\"ProcessingContext OK\")'" "Import ProcessingContext"
run_test "7.4" "python3 -c 'import audiomason; print(audiomason.__version__)'" "Import audiomason package"

# ═══════════════════════════════════════════
# SECTION 8: PluginLoader API
# ═══════════════════════════════════════════

echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "SECTION 8: PLUGINLOADER API" | tee -a "$OUTPUT_FILE"
echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

run_test "8.1" "python3 -c 'from audiomason.core import PluginLoader; loader = PluginLoader(); print(dir(loader))'" "PluginLoader attributes"
run_test "8.2" "python3 -c 'from audiomason.core import PluginLoader; loader = PluginLoader(); print(\"Has plugins attr:\", hasattr(loader, \"plugins\"))'" "Check plugins attribute"
run_test "8.3" "python3 -c 'from audiomason.core import PluginLoader; loader = PluginLoader(); print(\"Has get_plugin:\", hasattr(loader, \"get_plugin\"))'" "Check get_plugin method"

# ═══════════════════════════════════════════
# SECTION 9: Tests
# ═══════════════════════════════════════════

echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "SECTION 9: PYTEST" | tee -a "$OUTPUT_FILE"
echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

run_test "9.1" "find tests -name '*.py' | sort" "List all test files"
run_test "9.2" "find tests -name 'test_*.py' | sort" "List test_*.py files"
run_test "9.3" "pytest --collect-only 2>&1 | head -50" "Pytest collect tests"
run_test "9.4" "ls -la tests/" "tests directory structure"

# ═══════════════════════════════════════════
# SECTION 10: CLI Plugin Code
# ═══════════════════════════════════════════

echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "SECTION 10: CLI PLUGIN CODE INSPECTION" | tee -a "$OUTPUT_FILE"
echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

run_test "10.1" "grep -n 'def _web_command' plugins/cli/plugin.py" "Find _web_command definition"
run_test "10.2" "grep -A 5 'plugins_dir = Path' plugins/cli/plugin.py | head -20" "Check plugins_dir usage"
run_test "10.3" "grep -n 'def _tui_command' plugins/cli/plugin.py" "Find _tui_command definition"
run_test "10.4" "grep -n 'def _daemon_command' plugins/cli/plugin.py" "Find _daemon_command definition"
run_test "10.5" "wc -l plugins/cli/plugin.py" "CLI plugin line count"

# ═══════════════════════════════════════════
# SECTION 11: Dependencies
# ═══════════════════════════════════════════

echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "SECTION 11: DEPENDENCIES" | tee -a "$OUTPUT_FILE"
echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

run_test "11.1" "pip list | grep -E 'pyyaml|fastapi|uvicorn|pydantic|rich'" "Installed packages"
run_test "11.2" "which ffmpeg" "ffmpeg location"
run_test "11.3" "which ffprobe" "ffprobe location"
run_test "11.4" "ffmpeg -version 2>&1 | head -3" "ffmpeg version"

# ═══════════════════════════════════════════
# SECTION 12: Wizard Engine Code
# ═══════════════════════════════════════════

echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "SECTION 12: WIZARD ENGINE CODE" | tee -a "$OUTPUT_FILE"
echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

run_test "12.1" "grep -n 'loader.plugins' src/audiomason/wizard_engine.py" "Check loader.plugins usage"
run_test "12.2" "grep -n 'loader.get_plugin' src/audiomason/wizard_engine.py" "Check loader.get_plugin usage"
run_test "12.3" "wc -l src/audiomason/wizard_engine.py" "Wizard engine line count"

# ═══════════════════════════════════════════
# FINAL SUMMARY
# ═══════════════════════════════════════════

echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "TEST COMPLETE!" | tee -a "$OUTPUT_FILE"
echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"
echo "Results saved to: $OUTPUT_FILE" | tee -a "$OUTPUT_FILE"
echo "File size: $(du -h "$OUTPUT_FILE" | cut -f1)" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"
echo "To review:" | tee -a "$OUTPUT_FILE"
echo "  cat $OUTPUT_FILE" | tee -a "$OUTPUT_FILE"
echo "  less $OUTPUT_FILE" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"
echo "To upload to Claude:" | tee -a "$OUTPUT_FILE"
echo "  Upload this file in Claude interface" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

# Show summary of failed tests
echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
echo "QUICK SUMMARY - Non-zero exit codes:" | tee -a "$OUTPUT_FILE"
echo "════════════════════════════════════════════════" | tee -a "$OUTPUT_FILE"
grep "EXIT CODE: [1-9]" "$OUTPUT_FILE" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

echo "✅ Test script complete!"
echo "📄 Results: $OUTPUT_FILE"
