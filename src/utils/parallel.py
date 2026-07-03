"""非同期並列実行ユーティリティ。セマフォでAPIレート制限に対応。"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def run_with_semaphore(
    tasks: list[Awaitable[T]],
    max_concurrent: int = 5,
) -> list[T | Exception]:
    """タスクを最大 max_concurrent 並列で実行する。例外はそのまま結果リストに入れる。"""
    sem = asyncio.Semaphore(max_concurrent)

    async def _wrap(coro: Awaitable[T]) -> T | Exception:
        async with sem:
            try:
                return await coro
            except Exception as e:
                return e

    return await asyncio.gather(*[_wrap(t) for t in tasks])


async def retry_async(
    coro_fn: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> T:
    """指数バックオフ付きリトライ。"""
    for attempt in range(max_retries):
        try:
            return await coro_fn()
        except Exception:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(base_delay * (2 ** attempt))
    raise RuntimeError("unreachable")


def estimate_remaining_time(
    done: int,
    total: int,
    elapsed_seconds: float,
) -> float:
    """「このペースで全問処理すると残り何秒か」を推定する。"""
    if done == 0:
        return float("inf")
    rate = done / elapsed_seconds
    return (total - done) / rate
