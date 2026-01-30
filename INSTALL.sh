#!/bin/bash
# AudioMason v2 - Installation Script
# Quick and easy installation into your git tree

set -e  # Exit on error

echo "╔═══════════════════════════════════════════════╗"
echo "║   AudioMason v2 - Installation Script        ║"
echo "║   Version: 2.0.0 (98% Complete)              ║"
echo "╚═══════════════════════════════════════════════╝"
echo ""

# Detect git root
if [ -d ".git" ]; then
    GIT_ROOT="$(pwd)"
    echo "✓ Git repository detected: $GIT_ROOT"
else
    echo "✗ Error: Not in git repository root!"
    echo "  Please run this script from your git repository root."
    exit 1
fi

# Check if audiomason2-v2-complete.zip exists
if [ ! -f "audiomason-v2-complete.zip" ]; then
    echo "✗ Error: audiomason-v2-complete.zip not found!"
    echo "  Please place the ZIP file in the current directory."
    exit 1
fi

echo ""
echo "═══════════════════════════════════════════════"
echo "INSTALLATION PLAN"
echo "═══════════════════════════════════════════════"
echo ""
echo "Will extract and install:"
echo "  • src/audiomason/wizard_engine.py"
echo "  • plugins/cli/plugin.py (updated)"
echo "  • plugins/tui/* (new)"
echo "  • plugins/web_server/plugin.py (updated)"
echo "  • plugins/web_server/templates/index.html (updated)"
echo "  • wizards/* (5 new wizards)"
echo "  • docs/* (8 new documentation files)"
echo "  • test_web_ui.py (new)"
echo ""
read -p "Continue with installation? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Installation cancelled."
    exit 0
fi

echo ""
echo "═══════════════════════════════════════════════"
echo "CREATING BACKUP"
echo "═══════════════════════════════════════════════"

BACKUP_DIR="audiomason-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup files that will be overwritten
echo "Creating backup in: $BACKUP_DIR/"

if [ -f "plugins/cli/plugin.py" ]; then
    mkdir -p "$BACKUP_DIR/plugins/cli"
    cp plugins/cli/plugin.py "$BACKUP_DIR/plugins/cli/"
    echo "  ✓ Backed up: plugins/cli/plugin.py"
fi

if [ -f "plugins/web_server/plugin.py" ]; then
    mkdir -p "$BACKUP_DIR/plugins/web_server"
    cp plugins/web_server/plugin.py "$BACKUP_DIR/plugins/web_server/"
    echo "  ✓ Backed up: plugins/web_server/plugin.py"
fi

if [ -f "plugins/web_server/templates/index.html" ]; then
    mkdir -p "$BACKUP_DIR/plugins/web_server/templates"
    cp plugins/web_server/templates/index.html "$BACKUP_DIR/plugins/web_server/templates/"
    echo "  ✓ Backed up: plugins/web_server/templates/index.html"
fi

echo ""
echo "═══════════════════════════════════════════════"
echo "EXTRACTING FILES"
echo "═══════════════════════════════════════════════"

# Extract ZIP
unzip -o audiomason-v2-complete.zip

echo ""
echo "═══════════════════════════════════════════════"
echo "VERIFYING INSTALLATION"
echo "═══════════════════════════════════════════════"

# Check critical files
ERRORS=0

check_file() {
    if [ -f "$1" ]; then
        echo "  ✓ $1"
    else
        echo "  ✗ $1 - MISSING!"
        ERRORS=$((ERRORS + 1))
    fi
}

check_file "src/audiomason/wizard_engine.py"
check_file "plugins/cli/plugin.py"
check_file "plugins/tui/plugin.py"
check_file "plugins/tui/plugin.yaml"
check_file "plugins/web_server/templates/index.html"
check_file "wizards/quick_import.yaml"
check_file "wizards/batch_import.yaml"
check_file "wizards/complete_import.yaml"
check_file "wizards/merge_multipart.yaml"
check_file "wizards/advanced.yaml"
check_file "docs/WIZARD_ENGINE.md"
check_file "docs/TUI.md"
check_file "docs/FINAL_REPORT.md"
check_file "test_web_ui.py"

if [ $ERRORS -gt 0 ]; then
    echo ""
    echo "✗ Installation completed with $ERRORS errors!"
    echo "  Please check the missing files above."
    exit 1
fi

echo ""
echo "═══════════════════════════════════════════════"
echo "GIT STATUS"
echo "═══════════════════════════════════════════════"

# Show git status
git status --short

echo ""
echo "═══════════════════════════════════════════════"
echo "INSTALLATION COMPLETE!"
echo "═══════════════════════════════════════════════"
echo ""
echo "✅ Successfully installed AudioMason v2 components"
echo ""
echo "📦 What was installed:"
echo "  • Wizard Engine (420 lines)"
echo "  • Ncurses TUI Plugin (697 lines)"
echo "  • Updated CLI Plugin (wizard + tui support)"
echo "  • Updated Web UI (plugin/wizard/config management)"
echo "  • 5 Example Wizards (quick, batch, complete, merge, advanced)"
echo "  • 8 Documentation files"
echo "  • Test script"
echo ""
echo "🚀 Next steps:"
echo ""
echo "1. Review changes:"
echo "   git diff"
echo ""
echo "2. Test the new features:"
echo "   # Launch Terminal UI"
echo "   audiomason tui"
echo ""
echo "   # List wizards"
echo "   audiomason wizard"
echo ""
echo "   # Run a wizard"
echo "   audiomason wizard quick_import"
echo ""
echo "   # Start web UI"
echo "   audiomason web"
echo ""
echo "3. Commit changes:"
echo "   git add ."
echo "   git commit -m 'Add Wizard Engine and TUI interface'"
echo ""
echo "4. Read documentation:"
echo "   cat docs/FINAL_REPORT.md"
echo "   cat docs/WIZARD_ENGINE.md"
echo "   cat docs/TUI.md"
echo ""
echo "📋 Backup location:"
echo "   $BACKUP_DIR/"
echo ""
echo "═══════════════════════════════════════════════"
echo "Happy Processing! 🎧"
echo "═══════════════════════════════════════════════"
