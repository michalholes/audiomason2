"""API module for wizard management.

Provides REST API endpoints for managing wizards.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


class WizardAPI:
    """Wizard management API."""

    def __init__(self, wizards_dir: Path) -> None:
        """Initialize wizard API.

        Args:
            wizards_dir: Wizards directory
        """
        self.wizards_dir = wizards_dir
        self.wizards_dir.mkdir(parents=True, exist_ok=True)

    def list_wizards(self) -> list[dict[str, Any]]:
        """List all wizards.

        Returns:
            List of wizard info dicts
        """
        wizards = []
        
        for wizard_file in self.wizards_dir.glob("*.yaml"):
            import yaml
            with open(wizard_file) as f:
                wizard = yaml.safe_load(f)
            
            wizards.append({
                "name": wizard.get("wizard", {}).get("name", wizard_file.stem),
                "description": wizard.get("wizard", {}).get("description", ""),
                "filename": wizard_file.name,
                "steps": len(wizard.get("wizard", {}).get("steps", [])),
            })
        
        return wizards

    def get_wizard(self, name: str) -> dict[str, Any]:
        """Get wizard details.

        Args:
            name: Wizard filename (without .yaml)

        Returns:
            Wizard definition
        """
        wizard_file = self.wizards_dir / f"{name}.yaml"
        
        if not wizard_file.exists():
            raise FileNotFoundError(f"Wizard not found: {name}")
        
        import yaml
        with open(wizard_file) as f:
            return yaml.safe_load(f)

    def create_wizard(self, wizard_def: dict[str, Any]) -> dict[str, str]:
        """Create new wizard.

        Args:
            wizard_def: Wizard definition

        Returns:
            Success message
        """
        wizard_name = wizard_def.get("wizard", {}).get("name")
        if not wizard_name:
            raise ValueError("Wizard name is required")
        
        # Convert name to filename
        filename = wizard_name.lower().replace(" ", "_")
        wizard_file = self.wizards_dir / f"{filename}.yaml"
        
        if wizard_file.exists():
            raise FileExistsError(f"Wizard already exists: {wizard_name}")
        
        # Save wizard
        import yaml
        with open(wizard_file, "w") as f:
            yaml.safe_dump(wizard_def, f, default_flow_style=False)
        
        return {"message": f"Wizard '{wizard_name}' created", "filename": filename}

    def update_wizard(self, name: str, wizard_def: dict[str, Any]) -> dict[str, str]:
        """Update existing wizard.

        Args:
            name: Wizard filename (without .yaml)
            wizard_def: Wizard definition

        Returns:
            Success message
        """
        wizard_file = self.wizards_dir / f"{name}.yaml"
        
        if not wizard_file.exists():
            raise FileNotFoundError(f"Wizard not found: {name}")
        
        # Save wizard
        import yaml
        with open(wizard_file, "w") as f:
            yaml.safe_dump(wizard_def, f, default_flow_style=False)
        
        wizard_name = wizard_def.get("wizard", {}).get("name", name)
        return {"message": f"Wizard '{wizard_name}' updated"}

    def delete_wizard(self, name: str) -> dict[str, str]:
        """Delete wizard.

        Args:
            name: Wizard filename (without .yaml)

        Returns:
            Success message
        """
        wizard_file = self.wizards_dir / f"{name}.yaml"
        
        if not wizard_file.exists():
            raise FileNotFoundError(f"Wizard not found: {name}")
        
        wizard_file.unlink()
        
        return {"message": f"Wizard '{name}' deleted"}
