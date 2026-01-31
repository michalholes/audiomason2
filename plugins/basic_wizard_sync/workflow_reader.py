"""Configurable Workflow Reader - loads and executes YAML workflows."""

from __future__ import annotations

import re
import yaml
from pathlib import Path
from typing import Any, Optional


class WorkflowStep:
    """Single workflow step definition."""
    
    def __init__(self, data: dict):
        self.id = data['id']
        self.enabled = data.get('enabled', True)
        self.description = data.get('description', '')
        
        # Step type specific
        self.type = data.get('type')  # For preflight: menu, yes_no, input
        self.plugin = data.get('plugin')  # For processing: plugin name
        self.method = data.get('method')  # For processing: plugin method
        
        # Prompts
        self.prompt = data.get('prompt', '')
        self.default = data.get('default')
        self.required = data.get('required', False)
        
        # Hints
        self.hint_from = data.get('hint_from')
        self.hint_pattern = data.get('hint_pattern')
        
        # Conditions
        self.condition = data.get('condition')
        self.skip_if_set = data.get('skip_if_set', False)


class WorkflowConfig:
    """Workflow configuration from YAML."""
    
    def __init__(self, yaml_path: Path):
        """Load workflow from YAML file.
        
        Args:
            yaml_path: Path to workflow YAML
        """
        self.yaml_path = yaml_path
        self.data = self._load_yaml()
        
        # Parse workflow info
        workflow = self.data.get('workflow', {})
        self.name = workflow.get('name', 'Unnamed Workflow')
        self.description = workflow.get('description', '')
        
        # Parse steps
        self.preflight_steps = [
            WorkflowStep(step) 
            for step in workflow.get('preflight_steps', [])
        ]
        
        self.processing_steps = [
            WorkflowStep(step)
            for step in workflow.get('processing_steps', [])
        ]
        
        # Verbosity settings
        self.verbosity_config = self.data.get('verbosity', {})
    
    def _load_yaml(self) -> dict:
        """Load YAML file.
        
        Returns:
            Parsed YAML data
        """
        if not self.yaml_path.exists():
            raise FileNotFoundError(f"Workflow file not found: {self.yaml_path}")
        
        with open(self.yaml_path, 'r') as f:
            return yaml.safe_load(f)
    
    def get_enabled_preflight_steps(self) -> list[WorkflowStep]:
        """Get list of enabled preflight steps.
        
        Returns:
            List of enabled steps
        """
        return [step for step in self.preflight_steps if step.enabled]
    
    def get_enabled_processing_steps(self) -> list[WorkflowStep]:
        """Get list of enabled processing steps.
        
        Returns:
            List of enabled steps
        """
        return [step for step in self.processing_steps if step.enabled]
    
    def extract_hint(self, step: WorkflowStep, source_value: str) -> Optional[str]:
        """Extract hint from source value using regex pattern.
        
        Args:
            step: Workflow step with hint configuration
            source_value: Value to extract hint from
            
        Returns:
            Extracted hint or None
        """
        if not step.hint_pattern:
            return source_value
        
        try:
            match = re.search(step.hint_pattern, source_value)
            if match:
                return match.group(1).strip()
        except Exception:
            pass
        
        return source_value
    
    def evaluate_condition(
        self, 
        condition: Optional[str],
        context: dict
    ) -> bool:
        """Evaluate step condition.
        
        Args:
            condition: Condition string (e.g. "answers.publish == true")
            context: Context dict with 'answers', 'config', etc.
            
        Returns:
            True if condition met or no condition
        """
        if not condition:
            return True
        
        # Simple evaluation - supports:
        # - answers.key == value
        # - config.key == value
        # - answers.key != value
        
        try:
            # Parse condition
            if ' == ' in condition:
                left, right = condition.split(' == ', 1)
                left = left.strip()
                right = right.strip().strip('"\'')
                
                # Evaluate left side
                value = self._get_nested_value(left, context)
                
                # Convert right side
                if right.lower() == 'true':
                    right = True
                elif right.lower() == 'false':
                    right = False
                
                return value == right
            
            elif ' != ' in condition:
                left, right = condition.split(' != ', 1)
                left = left.strip()
                right = right.strip().strip('"\'')
                
                value = self._get_nested_value(left, context)
                
                if right.lower() == 'true':
                    right = True
                elif right.lower() == 'false':
                    right = False
                
                return value != right
        
        except Exception:
            return True
        
        return True
    
    def _get_nested_value(self, path: str, context: dict) -> Any:
        """Get nested value from context.
        
        Args:
            path: Dot-separated path (e.g. "answers.publish")
            context: Context dictionary
            
        Returns:
            Value at path or None
        """
        parts = path.split('.')
        current = context
        
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        
        return current
    
    def should_show_messages(self, verbosity: int, message_type: str) -> bool:
        """Check if message type should be shown at verbosity level.
        
        Args:
            verbosity: Verbosity level (0-3)
            message_type: Type of message (e.g. 'errors', 'prompts')
            
        Returns:
            True if should show
        """
        level_names = ['quiet', 'normal', 'verbose', 'debug']
        
        if verbosity < 0 or verbosity >= len(level_names):
            return False
        
        level_name = level_names[verbosity]
        allowed_types = self.verbosity_config.get(level_name, [])
        
        return message_type in allowed_types
