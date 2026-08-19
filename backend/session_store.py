"""In-memory session store for synthesis results (download support)."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from models import SynthesisResult


@dataclass
class _Entry:
    result: SynthesisResult
    created_at: float = field(default_factory=time.time)


_store: dict[str, _Entry] = {}
_LOCK = asyncio.Lock()
_TTL_S = 3600  # 1 hour


async def save(result: SynthesisResult) -> None:
    async with _LOCK:
        _store[result.session_id] = _Entry(result=result)


async def get(session_id: str) -> SynthesisResult | None:
    async with _LOCK:
        entry = _store.get(session_id)
        return entry.result if entry else None


async def sweep() -> None:
    """Remove sessions older than TTL."""
    now = time.time()
    async with _LOCK:
        expired = [k for k, v in _store.items() if now - v.created_at > _TTL_S]
        for k in expired:
            del _store[k]


async def run_sweeper() -> None:
    while True:
        await asyncio.sleep(300)
        await sweep()
