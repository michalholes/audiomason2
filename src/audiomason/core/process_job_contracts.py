"""Infrastructure-only PROCESS job contract dispatch table.

ASCII-only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

IMPORT_PROCESS_CONTRACT_ID = "plugins.import.process.v1"


@dataclass(frozen=True)
class ProcessJobContract:
    contract_id: str
    plugin_name: str
    entrypoint_name: str


_IMPORT_PROCESS_CONTRACT = ProcessJobContract(
    contract_id=IMPORT_PROCESS_CONTRACT_ID,
    plugin_name="import",
    entrypoint_name="run_process_contract",
)


def resolve_process_job_contract(meta: Mapping[str, str]) -> ProcessJobContract | None:
    contract_id = str(meta.get("contract_id") or "")
    if contract_id == IMPORT_PROCESS_CONTRACT_ID:
        return _IMPORT_PROCESS_CONTRACT
    return None


__all__ = [
    "IMPORT_PROCESS_CONTRACT_ID",
    "ProcessJobContract",
    "resolve_process_job_contract",
]
