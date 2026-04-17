# Бот БОБ

Telegram-бот, который в общем чате напоминает ученикам о сдаче домашнего задания по расписанию.

Подробнее:
- Памятка проекта → [Claude.md](Claude.md)
- Продуктовая идея → [PROJECT_IDEA.md](PROJECT_IDEA.md)
- Техническая спецификация → [TECH_SPEC.md](TECH_SPEC.md)

## Как работает

- Один процесс Python на Railway: aiogram (long-polling) + APScheduler в общем event-loop.
- Расписание — в [schedule.yaml](schedule.yaml) (на MVP-этапе, без БД).
- При старте процесс читает YAML и регистрирует cron-job'ы с `misfire_grace_time=300` (5 минут) — даже если случился кратковременный простой, напоминание всё равно уйдёт.
- Правка расписания: коммит + пуш в `main` → Railway автоматически передеплоит.

## Запуск локально

```bash
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
pip install -e .

cp .env.example .env        # и заполни TELEGRAM_BOT_TOKEN
python -m src.main
```

## Деплой на Railway

1. Подключить Railway-проект к GitHub-репо `kh93b69/BOB`, ветка `main`.
2. В Railway выставить переменные окружения:
   - `TELEGRAM_BOT_TOKEN` — от BotFather
   - `ADMIN_USER_IDS=494349908`
   - `DEFAULT_TIMEZONE=Asia/Almaty`
   - `LOG_LEVEL=INFO`
3. Railway использует [railway.toml](railway.toml) — startCommand: `python -m src.main`.
4. Пуш в `main` → автодеплой.

## Команды бота

| Команда | Где работает | Описание |
|---------|--------------|----------|
| `/start` | везде | приветствие |
| `/ping` | везде | проверка живости и текущее время бота |
| `/chatid` | в группе | возвращает `chat_id` — подставить в `schedule.yaml` |
| `/whoami` | везде | твой `user_id` и статус админа |
| `/jobs` | только админу в ЛС | список активных напоминаний и время следующих запусков |

## Типичный порядок настройки нового напоминания

1. Добавить бота в общий чат.
2. В чате написать `/chatid` → скопировать число.
3. Открыть [schedule.yaml](schedule.yaml), подставить `chat_id`, поправить `text` и `cron`, поставить `enabled: true`.
4. Коммит + пуш в `main`.
5. Railway передеплоит. Проверить логи в Railway UI.
6. В ЛС боту `/jobs` — убедиться, что job зарегистрирован с нужным `next_run`.

## cron-синтаксис (подсказка)

```
┌───── минута (0–59)
│ ┌─── час (0–23)
│ │ ┌─ день месяца (1–31)
│ │ │ ┌─ месяц (1–12)
│ │ │ │ ┌─ день недели (0–6, 0 = воскресенье)
│ │ │ │ │
0 19 * * *       # каждый день в 19:00
30 8 * * 1-5     # пн-пт в 08:30
0 18 * * 3,6     # ср и сб в 18:00
```
