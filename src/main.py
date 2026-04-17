import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import settings
from src.handlers import router
from src.schedule_loader import load_schedule
from src.scheduler_service import build_scheduler

scheduler_ref: AsyncIOScheduler | None = None


def _setup_logging() -> None:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def main() -> None:
    _setup_logging()
    log = logging.getLogger("bob")

    reminders = load_schedule(settings.schedule_file, settings.default_timezone)
    log.info("loaded %d reminders from %s", len(reminders), settings.schedule_file)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=None),
    )
    dp = Dispatcher()
    dp.include_router(router)

    global scheduler_ref
    scheduler = build_scheduler(bot, reminders)
    scheduler_ref = scheduler
    scheduler.start()

    me = await bot.get_me()
    log.info("bot started: @%s (id=%s)", me.username, me.id)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
