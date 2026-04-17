# Бот БОБ — техническая спецификация

## 1. Общая архитектура

```
┌─────────────────┐       ┌──────────────────────┐       ┌──────────────────┐
│   GitHub repo   │──push─▶│  Railway (worker)   │◀─SQL─▶│  Supabase (PG)   │
│  (main branch)  │       │  единый Python-      │       │  reminders, logs │
└─────────────────┘       │  процесс:            │       │  admins          │
                          │   - aiogram bot      │       └──────────────────┘
                          │   - APScheduler      │
                          │   - админ-хендлеры   │
                          └──────┬───────────────┘
                                 │ Telegram Bot API
                                 ▼
                          ┌──────────────────┐
                          │  общий чат с     │
                          │  Петром и Аником │
                          └──────────────────┘
```

**Принцип:** один долгоживущий процесс на Railway. Внутри — бот (long-polling) и планировщик, крутящиеся в одном event-loop.

**На этапе MVP БД не используется.** Расписание хранится в `schedule.yaml` в репо — правка = git push → автодеплой. Supabase подключим на этапе 2, когда админка начнёт создавать/редактировать напоминания через бота (Railway filesystem ephemeral, без внешнего хранилища изменения не переживут рестарт).

## 2. Стек

| Слой | Технология | Зачем |
|------|-----------|-------|
| Язык | Python 3.12 | асинхронность, зрелые Telegram-библиотеки |
| Бот | aiogram 3.x | современный async-фреймворк, FSM для админки |
| Планировщик | APScheduler 3.x | cron-триггеры, `misfire_grace_time` |
| БД | Supabase (PostgreSQL) | managed, бесплатный тариф, REST/SQL из коробки |
| Драйвер БД | `asyncpg` + `sqlalchemy[asyncio]` | async-доступ, миграции |
| Миграции | Alembic | версионирование схемы |
| Таймзоны | `pytz` / `zoneinfo` | жёсткая привязка ко времени |
| Конфиг | `pydantic-settings` + `.env` | валидация переменных окружения |
| Логи | `structlog` или stdlib `logging` | структурные логи → Railway Logs |
| Нейросеть (этап 3) | Anthropic SDK (Claude API) | функция «Нужна помощь» |

**Почему long-polling, а не webhooks:** на Railway уже крутится worker ради APScheduler, второй публичный HTTP-эндпоинт не нужен. Меньше движущихся частей — меньше точек отказа.

## 3. Структура репозитория

```
Бот БОБ/
├── Claude.md               # памятка
├── PROJECT_IDEA.md         # продуктовая идея
├── TECH_SPEC.md            # этот файл
├── README.md               # как запустить
├── pyproject.toml          # зависимости (или requirements.txt)
├── railway.toml            # конфиг деплоя Railway
├── .env.example            # шаблон переменных окружения
├── .gitignore
├── alembic.ini
├── migrations/             # миграции Alembic
└── src/
    ├── __init__.py
    ├── main.py             # точка входа: старт бота + планировщика
    ├── config.py           # настройки из env (pydantic-settings)
    ├── db/
    │   ├── engine.py       # asyncpg engine
    │   ├── models.py       # SQLAlchemy модели
    │   └── repo.py         # CRUD операции
    ├── bot/
    │   ├── dispatcher.py   # aiogram Dispatcher + middlewares
    │   ├── handlers/
    │   │   ├── common.py   # /start, /help для учеников
    │   │   ├── admin.py    # команды админа (этап 2)
    │   │   └── ai_help.py  # «Нужна помощь» (этап 3)
    │   ├── keyboards.py    # inline-клавиатуры админки
    │   └── states.py       # FSM-состояния для создания напоминаний
    ├── scheduler/
    │   ├── service.py      # APScheduler wrapper
    │   └── jobs.py         # функция отправки напоминания
    └── ai/                 # этап 3
        └── claude_client.py
```

## 4. Схема БД (Supabase / Postgres)

### Таблица `reminders`
| Поле | Тип | Описание |
|------|-----|----------|
| `id` | `uuid` PK | идентификатор |
| `chat_id` | `bigint` | куда слать (Telegram chat_id) |
| `message_text` | `text` | текст напоминания |
| `schedule_type` | `text` | `once` \| `daily` \| `weekly` \| `cron` |
| `cron_expression` | `text` nullable | для типа `cron` (5 полей) |
| `run_at` | `timestamptz` nullable | для типа `once` |
| `time_of_day` | `time` nullable | для `daily`/`weekly` |
| `weekdays` | `int[]` nullable | 0–6, для `weekly` |
| `timezone` | `text` | IANA-зона, напр. `Europe/Moscow` |
| `is_active` | `boolean` default `true` | можно временно выключить |
| `created_by` | `bigint` | telegram user_id админа |
| `created_at` | `timestamptz` default `now()` | |
| `updated_at` | `timestamptz` | |

### Таблица `admins`
| Поле | Тип | Описание |
|------|-----|----------|
| `telegram_user_id` | `bigint` PK | ID админа |
| `name` | `text` | подпись |
| `added_at` | `timestamptz` default `now()` | |

### Таблица `send_log`
| Поле | Тип | Описание |
|------|-----|----------|
| `id` | `bigserial` PK | |
| `reminder_id` | `uuid` FK → reminders | |
| `sent_at` | `timestamptz` default `now()` | факт отправки |
| `status` | `text` | `ok` \| `error` |
| `error_text` | `text` nullable | если `status=error` |

**Почему логируем отправки:** чтобы постфактум доказать, что напоминание ушло вовремя. Это прямой ответ на риск №1 «бот проспал».

## 5. Жизненный цикл напоминания

1. Админ в ЛС боту создаёт напоминание (FSM-диалог: текст → дата/время → таймзона → подтверждение).
2. Запись сохраняется в `reminders`, планировщику регистрируется job с тем же `id`.
3. В указанное время APScheduler вызывает `send_reminder(reminder_id)` → бот отправляет сообщение в `chat_id`.
4. Результат пишется в `send_log`. При ошибке — повтор через 30 секунд (максимум 3 попытки), параллельно уведомление админу в ЛС.
5. Для `once` — после успешной отправки `is_active=false`. Для периодических — job остаётся.

**Ключевая настройка APScheduler:** `misfire_grace_time=300` (5 минут). Если во время запланированного запуска шёл деплой или был рестарт, и реальное время отправки — в пределах 5 минут от плана, напоминание всё равно уйдёт.

**Загрузка job при старте:** при запуске процесса `scheduler.service` читает все `is_active=true` из `reminders` и регистрирует job в APScheduler. Это единственный источник правды — БД, in-memory jobstore заполняется из неё.

## 6. Переменные окружения

```
# MVP (этап 1):
TELEGRAM_BOT_TOKEN=         # от BotFather
ADMIN_USER_IDS=494349908    # через запятую, telegram user_id админов
DEFAULT_TIMEZONE=Asia/Almaty
LOG_LEVEL=INFO

# Этап 2 (админка, Supabase):
DATABASE_URL=               # postgresql+asyncpg://... от Supabase (pooler)
SUPABASE_SERVICE_KEY=       # service_role (только на сервере!)

# Этап 3 (нейросеть):
ANTHROPIC_API_KEY=
```

**Важно:** `SUPABASE_SERVICE_KEY` — только в Railway env. В репозиторий не коммитим. `.env` — в `.gitignore`, есть `.env.example` без значений.

## 7. Деплой

1. Репозиторий на GitHub, ветка `main`.
2. Railway проект подключён к GitHub → автодеплой на push в `main`.
3. `railway.toml` задаёт start command: `python -m src.main`.
4. Переменные окружения выставляются в Railway UI.
5. Миграции БД запускаются отдельной командой (`alembic upgrade head`) — либо вручную перед первым деплоем, либо как pre-start шаг.

**Устойчивость:** Railway перезапускает процесс при падении. APScheduler при старте читает актуальное расписание из БД — ни одно напоминание не теряется.

## 8. План реализации этапов

### Этап 1 — MVP (1 день, без БД)
- Скелет проекта в репо `kh93b69/BOB`: `pyproject.toml`, `src/`, `railway.toml`, `.gitignore`, `.env.example`, `schedule.yaml`.
- aiogram-бот: `/start` (приветствие), `/ping` (проверка живости), `/chatid` (возвращает `chat_id` — чтобы узнать id общей группы).
- `schedule.yaml` — список напоминаний (cron + текст + chat_id).
- APScheduler при старте читает YAML, регистрирует job’ы с `misfire_grace_time=300`.
- Функция `send_reminder` шлёт сообщение в `chat_id`, логирует результат в stdout (Railway Logs).
- Деплой на Railway, переменные окружения (`TELEGRAM_BOT_TOKEN`, `ADMIN_USER_IDS`, `DEFAULT_TIMEZONE=Asia/Almaty`) через UI.
- **Критерий готовности:** тестовое напоминание стабильно приходит в общий чат в заданное время 2–3 дня подряд.

### Этап 2 — Админка (2–3 дня)
- FSM-диалоги для создания/редактирования/удаления напоминаний.
- Команды: `/new`, `/list`, `/edit <id>`, `/delete <id>`, `/toggle <id>`.
- Проверка прав админа через `ADMIN_CHAT_IDS`.
- Уведомление админу в ЛС при ошибке отправки.
- **Критерий готовности:** админ без правки кода заводит напоминание и видит его срабатывание.

### Этап 3 — «Нужна помощь» (1–2 дня)
- Кнопка/команда `/help` в общем чате.
- Интеграция с Claude API (`claude-sonnet-4-6` по умолчанию — дёшево и быстро).
- Rate limit: 10 запросов в день на пользователя, настраивается.
- **Критерий готовности:** ученик задаёт вопрос, получает ответ за <10 сек.

## 9. Что понадобится от пользователя

На этапе планирования — ничего. Когда приступим к коду:

1. **Telegram bot token** — создать бота через [@BotFather](https://t.me/BotFather), прислать токен.
2. **Admin Telegram user ID** — числовой ID владельца (узнать через [@userinfobot](https://t.me/userinfobot)).
3. **Chat ID общего чата** — получим автоматически после добавления бота в чат (бот залогирует).
4. **Supabase credentials** — создадим проект, нужны `DATABASE_URL` и `SUPABASE_SERVICE_KEY`.
5. **GitHub classic token** — для создания репо и пушей (либо создадим руками, оба варианта ок).
6. **Railway project** — создадим и подключим к GitHub-репо.
7. **Таймзона учеников** — подтвердить `Europe/Moscow` или другая.

## 10. Открытые технические вопросы

- **Миграции на Railway.** Вариант А: прогонять `alembic upgrade head` перед стартом процесса (release command). Вариант Б: вручную из локали перед деплоем. Для двух пользователей — вариант Б проще, обсудим.
- **Секреты для Claude API.** Ключ генерируется в консоли Anthropic — понадобится на этапе 3, не раньше.
- **Резервное копирование БД.** Supabase делает автобэкапы на платных тарифах; на free — раз в неделю выгружать дамп в репо (по желанию).
