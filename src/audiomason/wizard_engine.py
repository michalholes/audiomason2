"""Wizard Engine - Execute YAML-based wizards.

This module provides a flexible wizard system that executes step-by-step
workflows defined in YAML files.
"""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any, Callable
from dataclasses import dataclass

from audiomason.core import ProcessingContext, PluginLoader, State
from audiomason.core.errors import AudioMasonError


class WizardError(AudioMasonError):
    """Wizard execution error."""

    pass


@dataclass
class StepResult:
    """Result from executing a wizard step."""

    success: bool
    value: Any = None
    error: str | None = None
    skip_remaining: bool = False


class WizardEngine:
    """Execute YAML-based wizards."""

    def __init__(self, loader: PluginLoader):
        """Initialize wizard engine.

        Args:
            loader: Plugin loader for executing plugin calls
        """
        self.loader = loader
        self.context: ProcessingContext | None = None
        self.user_input_handler: Callable | None = None
        self.progress_callback: Callable | None = None

    def set_input_handler(self, handler: Callable[[str, dict], str]):
        """Set custom input handler for interactive steps.

        Args:
            handler: Function that takes (prompt, options) and returns user input
        """
        self.user_input_handler = handler

    def set_progress_callback(self, callback: Callable[[str, int, int], None]):
        """Set progress callback.

        Args:
            callback: Function that takes (step_name, current, total)
        """
        self.progress_callback = callback

    def load_yaml(self, path: Path) -> dict:
        """Load wizard definition from YAML.

        Args:
            path: Path to wizard YAML file

        Returns:
            Wizard definition dictionary

        Raises:
            WizardError: If file not found or invalid YAML
        """
        if not path.exists():
            raise WizardError(f"Wizard file not found: {path}")

        try:
            with open(path, "r") as f:
                wizard_def = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise WizardError(f"Invalid YAML: {e}")

        # Validate structure
        if not isinstance(wizard_def, dict):
            raise WizardError("Wizard definition must be a dictionary")

        if "wizard" not in wizard_def:
            raise WizardError("Missing 'wizard' key in definition")

        wizard = wizard_def["wizard"]

        if "name" not in wizard:
            raise WizardError("Missing 'name' in wizard definition")

        if "steps" not in wizard or not wizard["steps"]:
            raise WizardError("Wizard must have at least one step")

        return wizard_def

    def execute_step(self, step: dict, context: ProcessingContext) -> StepResult:
        """Execute single wizard step.

        Args:
            step: Step definition
            context: Processing context

        Returns:
            StepResult with execution outcome
        """
        step_type = step.get("type", "input")
        step_id = step.get("id", "unknown")

        try:
            if step_type == "input":
                return self._execute_input_step(step, context)
            elif step_type == "choice":
                return self._execute_choice_step(step, context)
            elif step_type == "plugin_call":
                return self._execute_plugin_call(step, context)
            elif step_type == "condition":
                return self._execute_condition(step, context)
            elif step_type == "set_value":
                return self._execute_set_value(step, context)
            else:
                return StepResult(success=False, error=f"Unknown step type: {step_type}")
        except Exception as e:
            return StepResult(success=False, error=f"Step '{step_id}' failed: {str(e)}")

    def _execute_input_step(self, step: dict, context: ProcessingContext) -> StepResult:
        """Execute input step - ask user for text input.

        Args:
            step: Step definition
            context: Processing context

        Returns:
            StepResult with user input
        """
        prompt = step.get("prompt", "Enter value")
        required = step.get("required", False)
        default = step.get("default")
        validate = step.get("validate")

        # Use default value from preflight if specified
        if step.get("default_from") == "preflight":
            field = step.get("id")
            if hasattr(context, field):
                default = getattr(context, field)

        # Get user input
        if self.user_input_handler:
            options = {"required": required, "default": default, "validate": validate}
            value = self.user_input_handler(prompt, options)
        else:
            # Fallback to console input
            if default:
                prompt_text = f"{prompt} [{default}]: "
            else:
                prompt_text = f"{prompt}: "

            value = input(prompt_text).strip()
            if not value and default:
                value = default

        # Validate required
        if required and not value:
            fallback = step.get("fallback")
            if fallback:
                value = fallback
            else:
                return StepResult(success=False, error=f"Required field: {step.get('id')}")

        # Store in context
        field = step.get("id")
        if field:
            setattr(context, field, value)

        return StepResult(success=True, value=value)

    def _execute_choice_step(self, step: dict, context: ProcessingContext) -> StepResult:
        """Execute choice step - user selects from options.

        Args:
            step: Step definition
            context: Processing context

        Returns:
            StepResult with selected choice
        """
        prompt = step.get("prompt", "Select option")
        choices = step.get("choices", [])
        default = step.get("default")

        if not choices:
            return StepResult(success=False, error="No choices provided")

        # Get user choice
        if self.user_input_handler:
            options = {"choices": choices, "default": default, "type": "choice"}
            value = self.user_input_handler(prompt, options)
        else:
            # Fallback to console
            print(f"\n{prompt}")
            for i, choice in enumerate(choices, 1):
                marker = " (default)" if choice == default else ""
                print(f"  {i}. {choice}{marker}")

            choice_input = input("Select: ").strip()

            # Parse choice
            if choice_input.isdigit():
                idx = int(choice_input) - 1
                if 0 <= idx < len(choices):
                    value = choices[idx]
                else:
                    value = default
            else:
                value = choice_input if choice_input in choices else default

        # Store in context
        field = step.get("id")
        if field:
            setattr(context, field, value)

        return StepResult(success=True, value=value)

    def _execute_plugin_call(self, step: dict, context: ProcessingContext) -> StepResult:
        """Execute plugin call step.

        Args:
            step: Step definition
            context: Processing context

        Returns:
            StepResult with plugin call outcome
        """
        plugin_name = step.get("plugin")
        method = step.get("method", "process")
        params = step.get("params", {})

        if not plugin_name:
            return StepResult(success=False, error="No plugin specified")

        # Get plugin
        plugin = self.loader.plugins.get(plugin_name)
        if not plugin:
            return StepResult(success=False, error=f"Plugin not found: {plugin_name}")

        # Execute method
        try:
            if hasattr(plugin, method):
                result = getattr(plugin, method)(context, **params)
                return StepResult(success=True, value=result)
            else:
                return StepResult(success=False, error=f"Method not found: {plugin_name}.{method}")
        except Exception as e:
            return StepResult(success=False, error=f"Plugin call failed: {str(e)}")

    def _execute_condition(self, step: dict, context: ProcessingContext) -> StepResult:
        """Execute conditional step.

        Args:
            step: Step definition
            context: Processing context

        Returns:
            StepResult indicating which branch to take
        """
        condition = step.get("condition")
        if_true = step.get("if_true", [])
        if_false = step.get("if_false", [])

        # Evaluate condition
        result = self._evaluate_condition(condition, context)

        # Execute appropriate branch
        steps_to_execute = if_true if result else if_false

        for substep in steps_to_execute:
            step_result = self.execute_step(substep, context)
            if not step_result.success:
                return step_result

        return StepResult(success=True, value=result)

    def _evaluate_condition(self, condition: str, context: ProcessingContext) -> bool:
        """Evaluate condition string.

        Args:
            condition: Condition expression (e.g., "author == 'Unknown'")
            context: Processing context

        Returns:
            Boolean result
        """
        # Simple condition evaluator
        # Supports: field == value, field != value, field exists

        if not condition:
            return True

        # Parse condition
        if "==" in condition:
            field, value = condition.split("==")
            field = field.strip()
            value = value.strip().strip("\"'")
            return getattr(context, field, None) == value

        elif "!=" in condition:
            field, value = condition.split("!=")
            field = field.strip()
            value = value.strip().strip("\"'")
            return getattr(context, field, None) != value

        elif "exists" in condition:
            field = condition.replace("exists", "").strip()
            return hasattr(context, field) and getattr(context, field) is not None

        return True

    def _execute_set_value(self, step: dict, context: ProcessingContext) -> StepResult:
        """Execute set value step - set context attribute.

        Args:
            step: Step definition
            context: Processing context

        Returns:
            StepResult
        """
        field = step.get("field")
        value = step.get("value")

        if not field:
            return StepResult(success=False, error="No field specified")

        setattr(context, field, value)

        return StepResult(success=True, value=value)

    def run_wizard(
        self, wizard_def: dict, context: ProcessingContext | None = None
    ) -> ProcessingContext:
        """Run complete wizard.

        Args:
            wizard_def: Wizard definition (output from load_yaml)
            context: Optional existing context, creates new if None

        Returns:
            Processing context with results

        Raises:
            WizardError: If wizard execution fails
        """
        wizard = wizard_def["wizard"]
        steps = wizard["steps"]

        # Create or use existing context
        if context is None:
            context = ProcessingContext(id="wizard", source=Path("."), state=State.INIT)

        self.context = context

        # Execute steps
        total_steps = len(steps)
        for i, step in enumerate(steps, 1):
            step_id = step.get("id", f"step_{i}")

            # Progress callback
            if self.progress_callback:
                self.progress_callback(step_id, i, total_steps)

            # Execute step
            result = self.execute_step(step, context)

            if not result.success:
                error_msg = f"Wizard failed at step '{step_id}': {result.error}"
                context.state = State.ERROR
                context.add_error(error_msg)

                # Check if step has on_error handler
                on_error = step.get("on_error", "stop")
                if on_error == "continue":
                    continue
                elif on_error == "stop":
                    raise WizardError(error_msg)

            # Check if should skip remaining steps
            if result.skip_remaining:
                break

        # Mark as complete
        context.state = State.DONE

        return context

    def run_wizard_from_file(
        self, path: Path, context: ProcessingContext | None = None
    ) -> ProcessingContext:
        """Load and run wizard from YAML file.

        Args:
            path: Path to wizard YAML
            context: Optional existing context

        Returns:
            Processing context with results
        """
        wizard_def = self.load_yaml(path)
        return self.run_wizard(wizard_def, context)
