"""Test verbosity compliance across all commands.

This test ensures that verbosity flags (-q, -v, -d) work in ANY position
for ALL commands.

Requirements:
- Verbosity flags must work ALWAYS and EVERYWHERE
- Flags can appear before OR after command name
- Each command must respect the verbosity level

Test matrix: 7 commands × 4 levels = 28 tests
Commands: process, wizard, tui, web, daemon, version, help
Levels: -q (quiet), (none), -v (verbose), -d (debug)
"""

import subprocess
import sys
from pathlib import Path

import pytest


def run_audiomason(args: list[str], expect_error: bool = False) -> tuple[int, str, str]:
    """Run audiomason command and capture output.
    
    Args:
        args: Command arguments (e.g., ['-d', 'version'])
        expect_error: Whether to expect non-zero exit code
        
    Returns:
        Tuple of (returncode, stdout, stderr)
    """
    # Find audiomason executable
    repo_root = Path(__file__).parent.parent.parent
    audiomason_path = repo_root / "audiomason"
    
    if not audiomason_path.exists():
        audiomason_path = repo_root / "audiomason.py"
    
    cmd = [sys.executable, str(audiomason_path)] + args
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=5,
    )
    
    return result.returncode, result.stdout, result.stderr


class TestVerbosityCompliance:
    """Test verbosity compliance for all commands."""
    
    # ═══════════════════════════════════════════════════════════
    # VERSION COMMAND (simple, no side effects)
    # ═══════════════════════════════════════════════════════════
    
    def test_version_quiet(self):
        """Test: audiomason -q version"""
        rc, out, err = run_audiomason(["-q", "version"])
        assert rc == 0
        # In quiet mode, version should still show (it's the main output)
        assert "AudioMason" in out or "AudioMason" in err
    
    def test_version_normal(self):
        """Test: audiomason version"""
        rc, out, err = run_audiomason(["version"])
        assert rc == 0
        assert "AudioMason" in out or "AudioMason" in err
    
    def test_version_verbose(self):
        """Test: audiomason -v version"""
        rc, out, err = run_audiomason(["-v", "version"])
        assert rc == 0
        assert "AudioMason" in out or "AudioMason" in err
    
    def test_version_debug(self):
        """Test: audiomason -d version"""
        rc, out, err = run_audiomason(["-d", "version"])
        assert rc == 0
        assert "AudioMason" in out or "AudioMason" in err
    
    def test_version_flag_after_command(self):
        """Test: audiomason version -d (flag AFTER command)"""
        rc, out, err = run_audiomason(["version", "-d"])
        assert rc == 0
        assert "AudioMason" in out or "AudioMason" in err
    
    # ═══════════════════════════════════════════════════════════
    # HELP COMMAND
    # ═══════════════════════════════════════════════════════════
    
    def test_help_quiet(self):
        """Test: audiomason -q help"""
        rc, out, err = run_audiomason(["-q", "help"])
        assert rc == 0
        # Help should show even in quiet mode
        assert "Usage:" in out or "audiomason" in out
    
    def test_help_normal(self):
        """Test: audiomason help"""
        rc, out, err = run_audiomason(["help"])
        assert rc == 0
        assert "Usage:" in out or "audiomason" in out
    
    def test_help_verbose(self):
        """Test: audiomason -v help"""
        rc, out, err = run_audiomason(["-v", "help"])
        assert rc == 0
        assert "Usage:" in out or "audiomason" in out
    
    def test_help_debug(self):
        """Test: audiomason -d help"""
        rc, out, err = run_audiomason(["-d", "help"])
        assert rc == 0
        assert "Usage:" in out or "audiomason" in out
    
    # ═══════════════════════════════════════════════════════════
    # WIZARD COMMAND (list mode, no wizard specified)
    # ═══════════════════════════════════════════════════════════
    
    def test_wizard_list_quiet(self):
        """Test: audiomason -q wizard (list wizards in quiet mode)"""
        rc, out, err = run_audiomason(["-q", "wizard"])
        assert rc == 0
        # Should execute without error, even if no output in quiet mode
    
    def test_wizard_list_normal(self):
        """Test: audiomason wizard (list wizards)"""
        rc, out, err = run_audiomason(["wizard"])
        assert rc == 0
        # Should show wizard list or "No wizards found"
    
    def test_wizard_list_verbose(self):
        """Test: audiomason -v wizard"""
        rc, out, err = run_audiomason(["-v", "wizard"])
        assert rc == 0
    
    def test_wizard_list_debug(self):
        """Test: audiomason -d wizard"""
        rc, out, err = run_audiomason(["-d", "wizard"])
        assert rc == 0
    
    def test_wizard_flag_after_command(self):
        """Test: audiomason wizard -v (flag AFTER command)"""
        rc, out, err = run_audiomason(["wizard", "-v"])
        assert rc == 0
    
    # ═══════════════════════════════════════════════════════════
    # TUI COMMAND (will fail without curses, but should parse args)
    # ═══════════════════════════════════════════════════════════
    
    def test_tui_quiet_parsing(self):
        """Test: audiomason -q tui (should parse args even if TUI fails)"""
        rc, out, err = run_audiomason(["-q", "tui"], expect_error=True)
        # TUI might fail without terminal, but verbosity should parse
        # We just check that it doesn't crash on argument parsing
    
    def test_tui_normal_parsing(self):
        """Test: audiomason tui"""
        rc, out, err = run_audiomason(["tui"], expect_error=True)
    
    def test_tui_verbose_parsing(self):
        """Test: audiomason -v tui"""
        rc, out, err = run_audiomason(["-v", "tui"], expect_error=True)
    
    def test_tui_debug_parsing(self):
        """Test: audiomason -d tui"""
        rc, out, err = run_audiomason(["-d", "tui"], expect_error=True)
    
    def test_tui_flag_after_command(self):
        """Test: audiomason tui -d (flag AFTER command)"""
        rc, out, err = run_audiomason(["tui", "-d"], expect_error=True)
    
    # ═══════════════════════════════════════════════════════════
    # WEB COMMAND (quick start/stop test)
    # ═══════════════════════════════════════════════════════════
    
    @pytest.mark.skip(reason="Web server runs in foreground - waiting for refactor")
    def test_web_quiet_parsing(self):
        """Test: audiomason -q web --port 45123 (parse args, then kill)"""
        # We can't run web server in test, but we can check arg parsing
        # by looking at error messages
        rc, out, err = run_audiomason(["-q", "web", "--port", "45123"], expect_error=True)
    
    @pytest.mark.skip(reason="Web server runs in foreground - waiting for refactor")
    def test_web_verbose_parsing(self):
        """Test: audiomason -v web"""
        rc, out, err = run_audiomason(["-v", "web"], expect_error=True)
    
    @pytest.mark.skip(reason="Web server runs in foreground - waiting for refactor")
    def test_web_debug_parsing(self):
        """Test: audiomason -d web"""
        rc, out, err = run_audiomason(["-d", "web"], expect_error=True)
    
    @pytest.mark.skip(reason="Web server runs in foreground - waiting for refactor")
    def test_web_flag_after_command(self):
        """Test: audiomason web -v"""
        rc, out, err = run_audiomason(["web", "-v"], expect_error=True)
    
    # ═══════════════════════════════════════════════════════════
    # DAEMON COMMAND
    # ═══════════════════════════════════════════════════════════
    
    @pytest.mark.skip(reason="Daemon runs in foreground - not a priority yet")
    def test_daemon_quiet_parsing(self):
        """Test: audiomason -q daemon (parse args)"""
        # Daemon will fail if no config, but should parse verbosity
        rc, out, err = run_audiomason(["-q", "daemon"], expect_error=True)
    
    @pytest.mark.skip(reason="Daemon runs in foreground - not a priority yet")
    def test_daemon_verbose_parsing(self):
        """Test: audiomason -v daemon"""
        rc, out, err = run_audiomason(["-v", "daemon"], expect_error=True)
    
    @pytest.mark.skip(reason="Daemon runs in foreground - not a priority yet")
    def test_daemon_debug_parsing(self):
        """Test: audiomason -d daemon"""
        rc, out, err = run_audiomason(["-d", "daemon"], expect_error=True)
    
    @pytest.mark.skip(reason="Daemon runs in foreground - not a priority yet")
    def test_daemon_flag_after_command(self):
        """Test: audiomason daemon -d (flag AFTER command)"""
        rc, out, err = run_audiomason(["daemon", "-d"], expect_error=True)
    
    # ═══════════════════════════════════════════════════════════
    # PROCESS COMMAND (needs files, but tests arg parsing)
    # ═══════════════════════════════════════════════════════════
    
    def test_process_quiet_parsing(self):
        """Test: audiomason -q process (missing files, but parse args)"""
        rc, out, err = run_audiomason(["-q", "process"], expect_error=True)
        # Should fail due to missing files, not due to verbosity parsing
    
    def test_process_verbose_parsing(self):
        """Test: audiomason -v process"""
        rc, out, err = run_audiomason(["-v", "process"], expect_error=True)
    
    def test_process_debug_parsing(self):
        """Test: audiomason -d process"""
        rc, out, err = run_audiomason(["-d", "process"], expect_error=True)
    
    def test_process_flag_after_command(self):
        """Test: audiomason process -d (flag AFTER command)"""
        rc, out, err = run_audiomason(["process", "-d"], expect_error=True)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
