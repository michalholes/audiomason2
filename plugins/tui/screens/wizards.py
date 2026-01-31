"""Wizards management screen - FIX #10 (0 steps)."""

from __future__ import annotations

from pathlib import Path
import yaml

from ..menu import Menu, MenuItem
from ..dialogs import Dialogs
from ..theme import Theme


class WizardsScreen:
    """Wizards management screen."""
    
    def __init__(self, screen, theme: Theme, config: dict):
        """Initialize wizards screen.
        
        Args:
            screen: Curses screen
            theme: Theme manager
            config: TUI configuration
        """
        self.screen = screen
        self.theme = theme
        self.config = config
        self.menu = Menu(screen, theme)
        self.dialogs = Dialogs(screen, theme)
    
    def _count_wizard_steps(self, wizard_path: Path) -> int:
        """Count steps in wizard YAML.
        
        FIX #10: Correctly parse wizard structure.
        
        Args:
            wizard_path: Path to wizard YAML
            
        Returns:
            Number of steps
        """
        try:
            with open(wizard_path) as f:
                data = yaml.safe_load(f)
            
            # FIX: Parse structure correctly
            # Old code: steps = wizard.get('steps', 0)  # WRONG!
            # New code:
            wizard = data.get('wizard', {})
            steps = wizard.get('steps', [])
            
            if isinstance(steps, list):
                return len(steps)
            else:
                return 0
        except Exception:
            return 0
    
    def show(self) -> str:
        """Show wizards menu.
        
        Returns:
            Selected action or "back"
        """
        # Find wizards directory
        wizards_dir = Path(__file__).parent.parent.parent.parent.parent / "wizards"
        
        if not wizards_dir.exists():
            self.dialogs.message(
                "No Wizards",
                f"Wizards directory not found:\n{wizards_dir}"
            )
            return "back"
        
        # Load wizards
        wizard_files = sorted(wizards_dir.glob("*.yaml"))
        
        if not wizard_files:
            self.dialogs.message(
                "No Wizards",
                "No wizard files found.\n\nCreate wizards in:\n" + str(wizards_dir)
            )
            return "back"
        
        # Build menu items
        items = []
        for i, wizard_file in enumerate(wizard_files):
            # Load wizard metadata
            try:
                with open(wizard_file) as f:
                    wizard_data = yaml.safe_load(f)
                
                wizard = wizard_data.get('wizard', {})
                name = wizard.get('name', wizard_file.stem)
                desc = wizard.get('description', '')
                
                # FIX #10: Count steps correctly
                steps = self._count_wizard_steps(wizard_file)
                
                items.append(MenuItem(
                    key=str(i + 1),
                    label=f"{name} ({steps} steps)",
                    desc=desc[:50],
                    action=f"run:{wizard_file.stem}",
                    visible=True
                ))
            except Exception as e:
                items.append(MenuItem(
                    key=str(i + 1),
                    label=f"{wizard_file.stem} (error)",
                    desc=str(e)[:50],
                    action="",
                    visible=True
                ))
        
        # Add back option
        items.append(MenuItem(
            key="0",
            label="Back",
            desc="Return to main menu",
            action="back",
            visible=True
        ))
        
        # Show menu
        action = self.menu.show(
            title="Wizard Management",
            items=items,
            footer="<Select>                                             <Back>"
        )
        
        # Handle run action
        if action.startswith("run:"):
            wizard_name = action[4:]
            if self.dialogs.confirm(f"Run wizard '{wizard_name}'?", default=True):
                self.dialogs.message(
                    "Running Wizard",
                    f"Exit TUI and run:\n\n  audiomason wizard {wizard_name}"
                )
        
        return action
