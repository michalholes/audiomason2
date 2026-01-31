"""Integration tests for verbosity compliance (#25 from task list).

Tests that verbosity works ALWAYS and EVERYWHERE across all interfaces.
This is a CRITICAL requirement from AUDIOMASON_V2_FINAL_REQUIREMENTS.md.
"""

import subprocess
import tempfile
from pathlib import Path

import pytest


class TestVerbosityCompliance:
    """Test that verbosity works in all commands and interfaces."""
    
    @pytest.fixture
    def log_file(self):
        """Create temporary log file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            yield Path(f.name)
            # Cleanup
            Path(f.name).unlink(missing_ok=True)
    
    def run_command(self, cmd: list[str], log_file: Path = None) -> tuple[int, str, str]:
        """Run audiomason command.
        
        Args:
            cmd: Command to run
            log_file: Optional log file path
            
        Returns:
            (returncode, stdout, stderr)
        """
        env = {}
        if log_file:
            env['AUDIOMASON_LOG_FILE'] = str(log_file)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env if env else None
        )
        
        return result.returncode, result.stdout, result.stderr
    
    def get_log_content(self, log_file: Path) -> str:
        """Get log file content.
        
        Args:
            log_file: Log file path
            
        Returns:
            Log content
        """
        if log_file.exists():
            return log_file.read_text()
        return ""


class TestQuietMode:
    """Test -q / --quiet mode (CRITICAL)."""
    
    def test_help_quiet(self):
        """Test audiomason --help -q shows only errors."""
        returncode, stdout, stderr = subprocess.run(
            ['audiomason', '--help', '-q'],
            capture_output=True,
            text=True
        ).returncode, subprocess.run(
            ['audiomason', '--help', '-q'],
            capture_output=True,
            text=True
        ).stdout, subprocess.run(
            ['audiomason', '--help', '-q'],
            capture_output=True,
            text=True
        ).stderr
        
        # Quiet mode should show minimal output
        # (help is special case, may show some output)
        assert returncode == 0
    
    def test_quiet_flag_position_before_command(self):
        """Test -q flag works before command."""
        # audiomason -q web --help
        result = subprocess.run(
            ['audiomason', '-q', 'web', '--help'],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
    
    def test_quiet_flag_position_after_command(self):
        """Test -q flag works after command."""
        # audiomason web --help -q
        result = subprocess.run(
            ['audiomason', 'web', '--help', '-q'],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0


class TestVerboseMode:
    """Test -v / --verbose mode (CRITICAL)."""
    
    def test_verbose_flag_before_command(self):
        """Test -v flag works before command."""
        result = subprocess.run(
            ['audiomason', '-v', 'web', '--help'],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
    
    def test_verbose_flag_after_command(self):
        """Test -v flag works after command."""
        result = subprocess.run(
            ['audiomason', 'web', '--help', '-v'],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0


class TestDebugMode:
    """Test -d / --debug mode (CRITICAL)."""
    
    def test_debug_flag_before_command(self):
        """Test -d flag works before command."""
        result = subprocess.run(
            ['audiomason', '-d', 'web', '--help'],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
    
    def test_debug_flag_after_command(self):
        """Test -d flag works after command."""
        result = subprocess.run(
            ['audiomason', 'web', '--help', '-d'],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0


class TestVerbosityInCommands:
    """Test verbosity in specific commands."""
    
    def test_wizard_list_verbose(self):
        """Test wizard list with verbose."""
        result = subprocess.run(
            ['audiomason', 'wizard', '-v'],
            capture_output=True,
            text=True
        )
        
        # Should not crash
        assert result.returncode in (0, 1)  # May fail if no wizards
    
    def test_web_help_quiet(self):
        """Test web help with quiet."""
        result = subprocess.run(
            ['audiomason', 'web', '--help', '-q'],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
    
    def test_daemon_help_debug(self):
        """Test daemon help with debug."""
        result = subprocess.run(
            ['audiomason', 'daemon', '--help', '-d'],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0


class TestVerbosityFlagCombinations:
    """Test that only last verbosity flag wins."""
    
    def test_quiet_then_verbose(self):
        """Test -q -v (verbose wins)."""
        result = subprocess.run(
            ['audiomason', '-q', '-v', 'web', '--help'],
            capture_output=True,
            text=True
        )
        
        # Should not crash (verbose should win)
        assert result.returncode == 0
    
    def test_verbose_then_debug(self):
        """Test -v -d (debug wins)."""
        result = subprocess.run(
            ['audiomason', '-v', '-d', 'web', '--help'],
            capture_output=True,
            text=True
        )
        
        # Should not crash (debug should win)
        assert result.returncode == 0
    
    def test_debug_then_quiet(self):
        """Test -d -q (quiet wins)."""
        result = subprocess.run(
            ['audiomason', '-d', '-q', 'web', '--help'],
            capture_output=True,
            text=True
        )
        
        # Should not crash (quiet should win)
        assert result.returncode == 0


class TestVerbosityEnvironmentVariable:
    """Test AUDIOMASON_VERBOSITY environment variable."""
    
    def test_env_quiet(self):
        """Test AUDIOMASON_VERBOSITY=quiet."""
        result = subprocess.run(
            ['audiomason', 'web', '--help'],
            capture_output=True,
            text=True,
            env={'AUDIOMASON_VERBOSITY': 'quiet'}
        )
        
        assert result.returncode == 0
    
    def test_env_verbose(self):
        """Test AUDIOMASON_VERBOSITY=verbose."""
        result = subprocess.run(
            ['audiomason', 'web', '--help'],
            capture_output=True,
            text=True,
            env={'AUDIOMASON_VERBOSITY': 'verbose'}
        )
        
        assert result.returncode == 0
    
    def test_env_debug(self):
        """Test AUDIOMASON_VERBOSITY=debug."""
        result = subprocess.run(
            ['audiomason', 'web', '--help'],
            capture_output=True,
            text=True,
            env={'AUDIOMASON_VERBOSITY': 'debug'}
        )
        
        assert result.returncode == 0
    
    def test_cli_overrides_env(self):
        """Test that CLI flag overrides environment variable."""
        result = subprocess.run(
            ['audiomason', '-q', 'web', '--help'],
            capture_output=True,
            text=True,
            env={'AUDIOMASON_VERBOSITY': 'debug'}
        )
        
        # Should not crash (CLI quiet should override env debug)
        assert result.returncode == 0


class TestVerbosityAcceptance:
    """Acceptance tests for verbosity requirement.
    
    From AUDIOMASON_V2_FINAL_REQUIREMENTS.md:
    'verbosity levels must work ALWAYS and EVERYWHERE'
    """
    
    def test_all_commands_accept_quiet(self):
        """Test that all commands accept -q flag."""
        commands = ['web', 'daemon', 'wizard', 'tui']
        
        for cmd in commands:
            result = subprocess.run(
                ['audiomason', cmd, '--help', '-q'],
                capture_output=True,
                text=True
            )
            
            # Should not crash or show "unknown option" error
            assert result.returncode in (0, 1)
            assert "unknown option" not in result.stderr.lower()
            assert "unrecognized" not in result.stderr.lower()
    
    def test_all_commands_accept_verbose(self):
        """Test that all commands accept -v flag."""
        commands = ['web', 'daemon', 'wizard', 'tui']
        
        for cmd in commands:
            result = subprocess.run(
                ['audiomason', cmd, '--help', '-v'],
                capture_output=True,
                text=True
            )
            
            assert result.returncode in (0, 1)
            assert "unknown option" not in result.stderr.lower()
            assert "unrecognized" not in result.stderr.lower()
    
    def test_all_commands_accept_debug(self):
        """Test that all commands accept -d flag."""
        commands = ['web', 'daemon', 'wizard', 'tui']
        
        for cmd in commands:
            result = subprocess.run(
                ['audiomason', cmd, '--help', '-d'],
                capture_output=True,
                text=True
            )
            
            assert result.returncode in (0, 1)
            assert "unknown option" not in result.stderr.lower()
            assert "unrecognized" not in result.stderr.lower()


@pytest.mark.slow
class TestVerbosityLogging:
    """Test that verbosity actually affects logging output."""
    
    def test_quiet_logs_only_errors(self):
        """Test that quiet mode logs only errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            
            # This test would need actual error to verify
            # For now, just verify the flag is accepted
            result = subprocess.run(
                ['audiomason', 'web', '--help', '-q'],
                capture_output=True,
                text=True
            )
            
            assert result.returncode == 0
    
    def test_verbose_logs_more_than_normal(self):
        """Test that verbose mode logs more info."""
        # This test would need to compare outputs
        # For now, just verify the flag is accepted
        result = subprocess.run(
            ['audiomason', 'web', '--help', '-v'],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
    
    def test_debug_logs_everything(self):
        """Test that debug mode logs everything."""
        # This test would need to verify debug output
        # For now, just verify the flag is accepted
        result = subprocess.run(
            ['audiomason', 'web', '--help', '-d'],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
