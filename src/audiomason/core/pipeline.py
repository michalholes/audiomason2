"""Pipeline executor - YAML to DAG to async execution.

Reads declarative YAML pipeline definitions and executes them
as a DAG (Directed Acyclic Graph) with async and parallel support.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from audiomason.core.context import ProcessingContext
from audiomason.core.errors import PipelineError


@dataclass
class PipelineStep:
    """Single pipeline step definition."""

    id: str
    plugin: str
    interface: str
    after: list[str]  # Step dependencies
    parallel: bool = False


@dataclass
class Pipeline:
    """Pipeline definition."""

    name: str
    description: str
    steps: list[PipelineStep]


class PipelineExecutor:
    """Execute pipeline as DAG.

    Example YAML:
        pipeline:
          name: standard
          steps:
            - id: import
              plugin: audio_importer
              interface: IProcessor

            - id: convert
              plugin: audio_converter
              interface: IProcessor
              after: [import]

            - id: fetch_metadata
              plugin: metadata_fetcher
              interface: IProvider
              after: [import]
              parallel: true
    """

    def __init__(self, plugin_loader: Any) -> None:
        """Initialize pipeline executor.

        Args:
            plugin_loader: Plugin loader instance
        """
        self.plugin_loader = plugin_loader

    async def execute(self, pipeline: Pipeline, context: ProcessingContext) -> ProcessingContext:
        """Execute pipeline.

        Args:
            pipeline: Pipeline definition
            context: Initial context

        Returns:
            Final context after all steps

        Raises:
            PipelineError: If execution fails
        """
        # Build DAG
        dag = self._build_dag(pipeline.steps)

        # Execute topologically
        for level in dag:
            context = await self._execute_level(level, context)

        return context

    async def execute_from_yaml(
        self, yaml_path: Path, context: ProcessingContext
    ) -> ProcessingContext:
        """Load and execute pipeline from YAML file.

        Args:
            yaml_path: Path to pipeline YAML
            context: Initial context

        Returns:
            Final context

        Raises:
            PipelineError: If loading or execution fails
        """
        pipeline = self.load_pipeline(yaml_path)
        return await self.execute(pipeline, context)

    def load_pipeline(self, yaml_path: Path) -> Pipeline:
        """Load pipeline from YAML.

        Args:
            yaml_path: Path to YAML file

        Returns:
            Pipeline definition

        Raises:
            PipelineError: If loading fails
        """
        if not yaml_path.exists():
            raise PipelineError(f"Pipeline file not found: {yaml_path}")

        try:
            with open(yaml_path) as f:
                data = yaml.safe_load(f)

            if "pipeline" not in data:
                raise PipelineError("Invalid pipeline YAML: missing 'pipeline' key")

            pipeline_data = data["pipeline"]

            steps = []
            for step_data in pipeline_data.get("steps", []):
                step = PipelineStep(
                    id=step_data["id"],
                    plugin=step_data["plugin"],
                    interface=step_data["interface"],
                    after=step_data.get("after", []),
                    parallel=step_data.get("parallel", False),
                )
                steps.append(step)

            return Pipeline(
                name=pipeline_data.get("name", "unnamed"),
                description=pipeline_data.get("description", ""),
                steps=steps,
            )

        except Exception as e:
            raise PipelineError(f"Failed to load pipeline: {e}") from e

    def _build_dag(self, steps: list[PipelineStep]) -> list[list[PipelineStep]]:
        """Build DAG from steps using topological sort.

        Returns:
            List of levels, where each level contains steps that can run in parallel

        Raises:
            PipelineError: If DAG has cycles
        """
        # Build dependency graph
        step_map = {step.id: step for step in steps}
        in_degree = {step.id: 0 for step in steps}

        for step in steps:
            for dep in step.after:
                if dep not in step_map:
                    raise PipelineError(f"Step '{step.id}' depends on unknown step '{dep}'")
                in_degree[step.id] += 1

        # Topological sort (Kahn's algorithm)
        levels: list[list[PipelineStep]] = []
        remaining = set(step_map.keys())

        while remaining:
            # Find steps with no dependencies
            current_level = [
                step_map[step_id] for step_id in remaining if in_degree[step_id] == 0
            ]

            if not current_level:
                # Cycle detected
                raise PipelineError(f"Pipeline has circular dependencies: {remaining}")

            levels.append(current_level)

            # Remove from remaining
            for step in current_level:
                remaining.remove(step.id)

                # Decrease in-degree for dependent steps
                for other_step in steps:
                    if step.id in other_step.after:
                        in_degree[other_step.id] -= 1

        return levels

    async def _execute_level(
        self, steps: list[PipelineStep], context: ProcessingContext
    ) -> ProcessingContext:
        """Execute all steps in a level (potentially in parallel).

        Args:
            steps: Steps to execute
            context: Current context

        Returns:
            Updated context

        Raises:
            PipelineError: If any step fails
        """
        if not steps:
            return context

        # Separate parallel and sequential steps
        parallel_steps = [s for s in steps if s.parallel]
        sequential_steps = [s for s in steps if not s.parallel]

        # Execute sequential steps first
        for step in sequential_steps:
            context = await self._execute_step(step, context)

        # Execute parallel steps
        if parallel_steps:
            tasks = [self._execute_step(step, context) for step in parallel_steps]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check for errors
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    raise PipelineError(
                        f"Step '{parallel_steps[i].id}' failed: {result}"
                    ) from result

            # Use last result (all should have updated same context)
            if results:
                context = results[-1]  # type: ignore

        return context

    async def _execute_step(
        self, step: PipelineStep, context: ProcessingContext
    ) -> ProcessingContext:
        """Execute a single step.

        Args:
            step: Step to execute
            context: Current context

        Returns:
            Updated context

        Raises:
            PipelineError: If step fails
        """
        try:
            # Mark step as current
            context.current_step = step.id

            # Get plugin
            plugin = self.plugin_loader.get_plugin(step.plugin)

            # Execute based on interface
            if step.interface == "IProcessor":
                context = await plugin.process(context)
            elif step.interface == "IProvider":
                # Providers return data, not context
                # For now, just call fetch and ignore result
                # Real implementation would store result in context
                pass
            elif step.interface == "IEnricher":
                context = await plugin.enrich(context)
            else:
                raise PipelineError(f"Unknown interface: {step.interface}")

            # Mark step complete
            context.mark_step_complete(step.id)

            return context

        except Exception as e:
            raise PipelineError(f"Step '{step.id}' failed: {e}") from e
