import logging
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import settings

log = logging.getLogger(__name__)

router = Router(name="common")


def _is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in settings.admin_user_ids


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я БОБ — бот-напоминалка о сдаче домашнего задания.\n"
        "Я буду писать в общий чат по расписанию."
    )


@router.message(Command("ping"))
async def cmd_ping(message: Message, bot: Bot) -> None:
    me = await bot.get_me()
    now = datetime.now(tz=settings.tz).strftime("%Y-%m-%d %H:%M:%S %Z")
    await message.answer(
        f"pong\nбот: @{me.username}\nвремя ({settings.default_timezone}): {now}"
    )


@router.message(Command("chatid"))
async def cmd_chatid(message: Message) -> None:
    chat = message.chat
    title = chat.title or getattr(chat, "full_name", None) or "—"
    await message.answer(
        f"chat_id: {chat.id}\nтип: {chat.type}\nназвание: {title}"
    )
    log.info("chatid_requested", extra={"chat_id": chat.id, "type": chat.type})


@router.message(Command("whoami"))
async def cmd_whoami(message: Message) -> None:
    user = message.from_user
    if user is None:
        await message.answer("Не удалось определить пользователя.")
        return
    is_admin_flag = "да" if _is_admin(user.id) else "нет"
    username = f"@{user.username}" if user.username else "—"
    await message.answer(
        f"user_id: {user.id}\nusername: {username}\nадмин: {is_admin_flag}"
    )


@router.message(Command("jobs"), F.chat.type == "private")
async def cmd_jobs(message: Message, scheduler: AsyncIOScheduler | None = None) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return

    if scheduler is None:
        await message.answer("Планировщик ещё не поднят.")
        return

    jobs = scheduler.get_jobs()
    if not jobs:
        await message.answer("Активных напоминаний нет.")
        return

    lines = []
    for job in jobs:
        next_run = (
            job.next_run_time.strftime("%Y-%m-%d %H:%M %Z")
            if job.next_run_time
            else "—"
        )
        lines.append(f"• {job.id} → следующий запуск: {next_run}")
    await message.answer("\n".join(lines))
