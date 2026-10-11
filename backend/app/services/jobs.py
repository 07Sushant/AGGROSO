"""Background jobs (agent runs, screenshot extraction) on a small thread pool.

The app runs as one uvicorn worker, so a ThreadPoolExecutor is enough; jobs never block the
event loop. The caller's log context (request id, user) is copied into the job thread.
"""

from __future__ import annotations

import contextvars
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.config import get_settings

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="job")


def submit(fn: Callable[..., Any], *args: Any) -> None:
    if get_settings().agent_jobs_inline:  # tests: one SQLite connection, so no extra thread
        fn(*args)
        return
    ctx = contextvars.copy_context()
    _executor.submit(ctx.run, fn, *args)
