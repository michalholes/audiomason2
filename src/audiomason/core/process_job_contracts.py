"""Infrastructure-only PROCESS job contract dispatch table.

ASCII-only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

IMPORT_PROCESS_CONTRACT_ID = "plugins.import.process.v1"


@dataclass(frozen=True)
class ProcessJobContract:
    contract_id: str
    plugin_name: str
    entrypoint_name: str
    payload_meta_keys: tuple[str, ...]

    def bind_job_meta(self, meta: Mapping[str, Any]) -> dict[str, str]:
        bound: dict[str, str] = {"contract_id": self.contract_id}
        for key in self.payload_meta_keys:
            value = meta.get(key)
            if not isinstance(value, str) or not value:
                raise ValueError(f"missing required process contract binding: {key}")
            bound[key] = value
        override = meta.get("verbosity_override")
        if isinstance(override, str) and override:
            bound["verbosity_override"] = override
        return bound


_IMPORT_PROCESS_CONTRACT = ProcessJobContract(
    contract_id=IMPORT_PROCESS_CONTRACT_ID,
    plugin_name="import",
    entrypoint_name="run_process_contract",
    payload_meta_keys=("job_requests_path",),
)


def resolve_process_job_contract(meta: Mapping[str, Any]) -> ProcessJobContract | None:
    contract_id = str(meta.get("contract_id") or "")
    if contract_id == IMPORT_PROCESS_CONTRACT_ID:
        return _IMPORT_PROCESS_CONTRACT
    return None


__all__ = [
    "IMPORT_PROCESS_CONTRACT_ID",
    "ProcessJobContract",
    "resolve_process_job_contract",
]
