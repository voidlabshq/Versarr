"""Benchmark one-shot scan throughput against a configured library root."""

from __future__ import annotations

import asyncio
import time

from versarr.bootstrap import create_runtime
from versarr.config import load_settings


async def _main() -> None:
    runtime = create_runtime(load_settings())
    started = time.perf_counter()
    await runtime.run_scan_once()
    duration = time.perf_counter() - started
    print(f"scan_completed_seconds={duration:.3f}")


if __name__ == "__main__":
    asyncio.run(_main())

