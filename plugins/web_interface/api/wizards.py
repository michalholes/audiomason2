from __future__ import annotations

from fastapi import FastAPI


def mount_wizards(_app: FastAPI) -> None:
    """Legacy wizard API endpoints have been removed.

    Wizard platform ownership is restricted to the Import plugin.
    This function remains only to keep the web_interface plugin import graph stable.
    """

    return None
