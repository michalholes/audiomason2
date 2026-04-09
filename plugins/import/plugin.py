"""Import plugin entrypoint.

This plugin currently provides only the ImportWizardEngine.

ASCII-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from audiomason.core.config import ConfigResolver
from audiomason.core.loader import PluginLoader

from . import processed_registry_required
from .cli import import_cli_main
from .detached_runtime import resolve_phase2_runtime
from .engine import ImportWizardEngine
from .process_contract_completion import run_process_contract_completion
from .ui_api import build_router


def load_import_owned_plugin(name: str) -> Any:
    plugins_root = Path(__file__).resolve().parents[1]
    loader = PluginLoader(builtin_plugins_dir=plugins_root)
    return loader.load_plugin(plugins_root / name, validate=False)


async def run_import_owned_plugin_job(
    *,
    plugin_name: str,
    job: dict[str, Any],
    plugin: Any | None = None,
) -> dict[str, Any]:
    plugin_obj = plugin if plugin is not None else load_import_owned_plugin(plugin_name)
    runner = plugin_obj._execute_job
    result = await runner(dict(job))
    if not isinstance(result, dict):
        raise RuntimeError(f"provider_job_invalid_result:{plugin_name}")
    return dict(result)


class ImportPlugin:
    """Import plugin providing the ImportWizardEngine."""

    def __init__(self, resolver: ConfigResolver | None = None) -> None:
        # Fallback resolver is for tests only. Real hosts must provide a resolver.
        self._resolver = resolver or ConfigResolver(cli_args={})
        self.engine = ImportWizardEngine(resolver=self._resolver)
        processed_registry_required._install_processed_registry_subscriber(resolver=self._resolver)

    async def run_process_contract(
        self, *, job_id: str, job_meta: dict[str, object], plugin_loader: object
    ) -> None:
        runtime = resolve_phase2_runtime(live_engine=self.engine, job_meta=dict(job_meta))
        await run_process_contract_completion(
            engine=runtime,
            job_id=job_id,
            job_meta=dict(job_meta),
            plugin_loader=plugin_loader,
        )

    def get_engine(self) -> ImportWizardEngine:
        return self.engine

    def get_cli_commands(self) -> dict[str, object]:
        """Return plugin-provided CLI command handlers.

        This plugin provides the top-level 'import' command.
        """

        return {
            "import": lambda argv: import_cli_main(
                argv,
                engine=self.engine,
                resolver=self._resolver,
            )
        }

    def get_fastapi_router(self):
        """Return the import UI router (host must mount it)."""

        return build_router(engine=self.engine)


__all__ = ["ImportPlugin", "run_import_owned_plugin_job"]
