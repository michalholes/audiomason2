from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

_T = TypeVar("_T")


async def to_thread(fn: Callable[..., _T], /, *args: object, **kwargs: object) -> _T:
    return await asyncio.to_thread(fn, *args, **kwargs)
