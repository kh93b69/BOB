import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.schedule_loader import ReminderConfig

log = logging.getLogger(__name__)

MISFIRE_GRACE_SECONDS = 300


async def _send_reminder(bot: Bot, reminder: ReminderConfig) -> None:
    try:
        await bot.send_message(chat_id=reminder.chat_id, text=reminder.text)
        log.info(
            "reminder_sent",
            extra={"reminder_id": reminder.id, "chat_id": reminder.chat_id},
        )
    except TelegramAPIError:
        log.exception(
            "reminder_failed",
            extra={"reminder_id": reminder.id, "chat_id": reminder.chat_id},
        )


def build_scheduler(bot: Bot, reminders: list[ReminderConfig]) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    for r in reminders:
        if not r.enabled:
            log.info("reminder_skipped_disabled", extra={"reminder_id": r.id})
            continue

        trigger = CronTrigger.from_crontab(r.cron, timezone=r.timezone)
        scheduler.add_job(
            _send_reminder,
            trigger=trigger,
            id=r.id,
            args=[bot, r],
            misfire_grace_time=MISFIRE_GRACE_SECONDS,
            coalesce=True,
            replace_existing=True,
        )
        log.info(
            "reminder_scheduled",
            extra={
                "reminder_id": r.id,
                "cron": r.cron,
                "timezone": r.timezone,
                "chat_id": r.chat_id,
            },
        )

    return scheduler
