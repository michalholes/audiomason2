"""BadGuys tests package.

This module intentionally re-exports stable symbols used by test modules.
"""

from badguys.discovery import discover_tests

__all__ = ["discover_tests"]
