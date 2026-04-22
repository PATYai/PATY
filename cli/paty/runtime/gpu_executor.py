"""Dedicated single-thread executor for MLX/Metal work.

Metal's command queues expect all operations on a given queue to be
issued from the same OS thread.  Using asyncio's default thread pool
lets STT and TTS work bounce between worker threads, which can trip
Metal assertions such as:

    'A command encoder is already encoding to this command buffer'
    'Completed handler provided after commit call'

This module provides a ``ThreadPoolExecutor`` with ``max_workers=1``
shared by STT and TTS services.  Because there is only one worker,
MLX calls are inherently serialized and always run on the same OS
thread — no additional lock required.

Future direction: replace with separate MLX contexts / Metal command
queues per service, or isolate services into separate processes.  The
consumer interface (pass executor to ``loop.run_in_executor``) stays
the same either way.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor


def create_gpu_executor() -> ThreadPoolExecutor:
    """Create a single-worker executor for serializing MLX/Metal access."""
    return ThreadPoolExecutor(max_workers=1, thread_name_prefix="paty-mlx")
