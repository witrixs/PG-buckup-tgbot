from __future__ import annotations

import logging
from datetime import time
from zoneinfo import ZoneInfo

from telegram.ext import Application

from bot.config import Settings
from bot.handlers import scheduled_backup

logger = logging.getLogger(__name__)


def setup_scheduler(application: Application, settings: Settings) -> None:
    if not settings.schedule_enabled:
        logger.info("Scheduled backup is disabled")
        return

    if application.job_queue is None:
        raise RuntimeError("JobQueue is not available. Install python-telegram-bot[job-queue]")

    tz = ZoneInfo(settings.timezone)
    application.job_queue.run_daily(
        scheduled_backup,
        time=time(hour=settings.schedule_hour, minute=settings.schedule_minute, tzinfo=tz),
        name="daily_backup",
    )
    logger.info(
        "Scheduled backup enabled: daily at %02d:%02d (%s)",
        settings.schedule_hour,
        settings.schedule_minute,
        settings.timezone,
    )
