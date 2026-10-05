#!/usr/bin/env python3
"""Boots the BullMQ video-render worker against a Redis connection."""
from __future__ import annotations
import logging
import os
from workers.worker import VideoWorker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("workers")

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")

if __name__ == "__main__":
    worker = VideoWorker(
        "video:render",
        connection={"host": "127.0.0.1", "port": 6379},
        concurrency=2,
    )
    logger.info("video worker listening on queue 'video:render' (Redis: %s)", REDIS_URL)
    try:
        worker.run()
    except KeyboardInterrupt:
        logger.info("worker stopped")
        worker.close()
