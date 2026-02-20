"""File-IO facade for the import plugin.

This module centralizes imports from plugins.file_io so that other modules in
plugins.import do not directly depend on multiple external areas.

ASCII-only.
"""

from __future__ import annotations

from plugins.file_io.service import FileService
from plugins.file_io.service.types import RootName


def file_service_from_resolver(resolver):
    return FileService.from_resolver(resolver)


ROOT_MAP = {rn.value: rn for rn in RootName}
