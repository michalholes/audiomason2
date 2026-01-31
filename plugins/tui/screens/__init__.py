"""TUI screens."""

from .main import MainScreen
from .wizards import WizardsScreen
from .config import ConfigScreen
from .plugins import PluginsScreen
from .web import WebScreen
from .daemon import DaemonScreen
from .logs import LogsScreen
from .about import AboutScreen

__all__ = [
    "MainScreen",
    "WizardsScreen",
    "ConfigScreen",
    "PluginsScreen",
    "WebScreen",
    "DaemonScreen",
    "LogsScreen",
    "AboutScreen",
]
