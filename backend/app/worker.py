from __future__ import annotations

import asyncio
import signal

from app.bootstrap import bootstrap_database
from app.config import get_settings
from app.main import build_v2_service, build_v3_service


async def run_worker() -> None:
    bootstrap_database()
    settings = get_settings()
    v2_service = build_v2_service(settings, auto_start=True)
    v3_service = build_v3_service(settings, auto_start=True)
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stopping.set)
        except NotImplementedError:
            pass
    try:
        while not stopping.is_set():
            await asyncio.gather(
                v2_service.recover_pending_jobs(),
                v3_service.recover_pending_jobs(),
            )
            try:
                await asyncio.wait_for(stopping.wait(), timeout=1.5)
            except TimeoutError:
                continue
    finally:
        await asyncio.gather(v2_service.shutdown(), v3_service.shutdown())


if __name__ == "__main__":
    asyncio.run(run_worker())
