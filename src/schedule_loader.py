from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml


@dataclass(frozen=True, slots=True)
class ReminderConfig:
    id: str
    chat_id: int
    text: str
    cron: str
    timezone: str
    enabled: bool = True


ScheduleType = Literal["cron"]


def load_schedule(path: Path, default_timezone: str) -> list[ReminderConfig]:
    if not path.exists():
        raise FileNotFoundError(f"Файл расписания не найден: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = raw.get("reminders") or []

    reminders: list[ReminderConfig] = []
    seen_ids: set[str] = set()
    for item in items:
        rid = str(item["id"])
        if rid in seen_ids:
            raise ValueError(f"Дубликат id напоминания: {rid}")
        seen_ids.add(rid)

        reminders.append(
            ReminderConfig(
                id=rid,
                chat_id=int(item["chat_id"]),
                text=str(item["text"]),
                cron=str(item["cron"]),
                timezone=str(item.get("timezone") or default_timezone),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return reminders
