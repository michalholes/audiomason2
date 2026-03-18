"""Import plugin entrypoint.

This plugin currently provides only the ImportWizardEngine.

ASCII-only.
"""

from __future__ import annotations

from audiomason.core.config import ConfigResolver

from . import processed_registry_required
from .cli import import_cli_main
from .detached_runtime import resolve_phase2_runtime
from .engine import ImportWizardEngine
from .process_contract_completion import run_process_contract_completion
from .ui_api import build_router


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
