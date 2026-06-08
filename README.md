# 🛡 PostgreSQL Backup Bot — Telegram-бот для резервного копирования

> Telegram-бот для автоматического и ручного backup PostgreSQL: `pg_dump`, проверка целостности, отправка файлов в чат, расписание и управление через inline-меню.

---

## 📋 Содержание

- [Технологический стек](#технологический-стек)
- [Требования](#требования)
- [Установка и запуск](#установка-и-запуск)
- [Конфигурация](#конфигурация)
- [Основные функции](#основные-функции)
- [Команды бота](#команды-бота)
- [Структура проекта](#структура-проекта)
- [Развертывание](#развертывание)

---

## 🛠️ Технологический стек

### Backend
- **Python 3.12** — язык разработки
- **python-telegram-bot 21.x** — Telegram Bot API с JobQueue
- **python-dotenv** — загрузка переменных окружения
- **pg_dump / pg_restore** — утилиты PostgreSQL для backup и проверки

### Инфраструктура
- **Docker / Docker Compose** — контейнеризация с несколькими версиями PG-клиентов
- **PostgreSQL** — целевые базы данных для резервного копирования

---

## 📦 Требования

### Локальный запуск
- Python 3.11+
- pip
- PostgreSQL client tools (`pg_dump`, `pg_restore`) для нужных версий
- Доступ к PostgreSQL на сервере (peer-auth через sudo или TCP с паролем)

### Docker (рекомендуется)
- Docker 20+
- Docker Compose v2

---

## 🚀 Установка и запуск

### 1. Клонирование репозитория

```bash
git clone https://github.com/witrixs/PG-buckup-tgbot
cd PG-buckup-tgbot
```

### 2. Конфигурация

Создайте файл `.env` в корне проекта (см. раздел [Конфигурация](#конфигурация)).

### 3. Запуск через Docker (рекомендуется)

```bash
# Сборка и запуск
docker compose up -d --build

# Просмотр логов
docker compose logs -f

# Перезапуск после изменения .env
docker compose up -d --build
```

Контейнер использует `network_mode: host` для доступа к PostgreSQL на localhost.

### 4. Локальный запуск (без Docker)

```bash
# Создание виртуального окружения
python -m venv venv

# Активация
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt

# Запуск (на сервере с PostgreSQL, при USE_SUDO=true — от root)
python main.py
```

---

## ⚙️ Конфигурация

Создайте файл `.env` в корне проекта:

```env
# Telegram
BOT_TOKEN="bot-token-here"

# Кто может управлять ботом (Telegram user id через запятую)
ADMIN_IDS="3242432423,4234234324"

# Куда отправлять backup-файлы (личный чат, группа или канал)
# Если не указано — используется первый id из ADMIN_IDS
BACKUP_CHAT_ID="-103626872433"

# PostgreSQL базы: имя:версия через запятую
DATABASES="postgres_db:18"

# Или JSON:
# DATABASES='[{"name":"postgres_db","postgres_version":"18"},{"name":"postgrestest_db","postgres_version":"18"}]'

# Пути (для Docker — как в docker-compose.yml)
BACKUP_DIR="/backups"
LOG_FILE="/var/log/pg_backup_telegram.log"

# Лимиты хранилища (GB). 0 = без ограничений
BACKUP_MAX_SIZE_GB=1
LOG_MAX_SIZE_GB=1

# PostgreSQL
POSTGRES_BIN_BASE="/usr/lib/postgresql"
POSTGRES_USER="postgres"
USE_SUDO=false

# Подключение к PostgreSQL (для Docker)
PGHOST="127.0.0.1"
PGPORT="5432"
PGPASSWORD="your-password"

# Часовой пояс контейнера (имена файлов, логи, datetime)
TZ="Europe/Moscow"

# Расписание (ежедневный backup)
SCHEDULE_ENABLED=true
SCHEDULE_HOUR=22
SCHEDULE_MINUTE=0
TIMEZONE="Europe/Moscow"
```

### Пояснения к ключевым переменным

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Токен бота от [@BotFather](https://t.me/BotFather) |
| `ADMIN_IDS` | Telegram user ID администраторов (через запятую) |
| `BACKUP_CHAT_ID` | Чат, куда отправляются backup-файлы и уведомления. Получить: `/chatid` |
| `DATABASES` | Список баз в формате `имя:версия` или JSON-массив |
| `USE_SUDO` | `true` на хосте с peer-auth, `false` в Docker |
| `PGHOST` | Хост PostgreSQL. В Docker используйте `127.0.0.1` или TCP |
| `PGPASSWORD` | Пароль для TCP-подключения (если нужен) |

⚠️ **Важно**: Никогда не публикуйте файл `.env` с реальными ключами!

### Версии PostgreSQL в Docker

В `docker-compose.yml` укажите нужные версии клиентов:

```yaml
build:
  args:
    PG_CLIENT_VERSIONS: "16 17 18"
```

Версия в `DATABASES` должна совпадать с установленной в контейнере.

---

## ✨ Основные функции

### Backup
- 💾 **Ручной backup** — все базы или одну через inline-меню или команды
- ⏰ **Автоматический backup** — ежедневно по расписанию (JobQueue)
- 📦 **Формат pg_dump** — `-Fc -b -v` (custom format, blobs, verbose)
- ✅ **Проверка целостности** — `pg_restore -l` после каждого backup
- 📤 **Отправка в Telegram** — файлы `.backup` приходят в чат

### Управление
- 🎛️ **Inline-меню** — полное управление без запоминания команд
- 🗄 **Несколько баз** — каждая со своей версией PostgreSQL
- 📁 **История backup** — просмотр, пагинация, повторная отправка файлов
- 📊 **Статус системы** — хост, расписание, хранилище, состояние задач
- 🔒 **Доступ только для админов** — по `ADMIN_IDS`

### Хранилище
- 🧹 **Автоочистка backup** — удаление старых файлов при превышении лимита
- 📝 **Ротация логов** — ограничение размера лог-файлов
- 📂 **Локальное хранение** — backup сохраняются на диске сервера

### Уведомления
- 🟢 **Стартовое сообщение** — при запуске бота в `BACKUP_CHAT_ID`
- 🔄 **Прогресс backup** — live-обновление статуса в чате
- ❌ **Ошибки** — подробное сообщение при сбое

---

## 🤖 Команды бота

| Команда | Описание |
|---|---|
| `/start`, `/menu` | Главное меню управления |
| `/backup` | Backup всех настроенных баз |
| `/backup_db <имя>` | Backup одной базы |
| `/databases` | Список баз и статус pg_dump |
| `/status` | Статус системы и хранилища |
| `/chatid` | ID текущего чата (для `BACKUP_CHAT_ID`) |
| `/help` | Справка по разделам |

Доступ ко всем командам только у пользователей из `ADMIN_IDS`.

---

## 📁 Структура проекта

```
PG-buckup-tgbot/
├── bot/
│   ├── ui/
│   │   ├── keyboards.py      # Inline-клавиатуры меню
│   │   └── messages.py       # Тексты сообщений (HTML)
│   ├── backup.py             # pg_dump, проверка, история файлов
│   ├── config.py             # Загрузка и парсинг .env
│   ├── handlers.py           # Команды и callback-обработчики
│   ├── logging_setup.py      # Настройка логирования
│   ├── main.py               # Точка входа бота
│   ├── scheduler.py          # Ежедневное расписание backup
│   └── storage.py            # Очистка backup и логов
├── backups/                  # Локальные backup-файлы (volume)
├── logs/                     # Лог-файлы (volume)
├── main.py                   # Запуск: python main.py
├── Dockerfile                # Образ с PG-клиентами
├── docker-compose.yml        # Docker Compose конфигурация
├── requirements.txt          # Python зависимости
└── .env                      # Конфигурация (не в git)
```

---

## 🛠️ Основные команды

### Docker

```bash
# Запуск
docker compose up -d --build

# Логи
docker compose logs -f backup-bot

# Остановка
docker compose down

# Пересборка после изменений
docker compose up -d --build
```

### Локально

```bash
# Запуск бота
python main.py

# Активация venv (Linux)
source venv/bin/activate && python main.py
```

---

## 🚢 Развертывание

### Docker Compose (рекомендуется)

1. Скопируйте проект на сервер с PostgreSQL
2. Создайте `.env` с токеном, admin ID и списком баз
3. Убедитесь, что `PG_CLIENT_VERSIONS` в `docker-compose.yml` покрывает версии из `DATABASES`
4. Запустите:

```bash
docker compose up -d --build
```

5. Напишите боту `/start`, затем `/chatid` в нужном чате и пропишите `BACKUP_CHAT_ID` в `.env`
6. Перезапустите контейнер

### Запуск на хосте (без Docker)

Подходит, если PostgreSQL установлен локально и используется peer-authentication:

```env
USE_SUDO=true
PGHOST=/var/run/postgresql
BACKUP_DIR=/root
LOG_FILE=/var/log/pg_backup_telegram.log
```

Запуск от root:

```bash
sudo python main.py
```

### Systemd сервис

Создайте `/etc/systemd/system/pg-backup-bot.service`:

```ini
[Unit]
Description=PostgreSQL Backup Telegram Bot
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/PG-buckup-tgbot
EnvironmentFile=/path/to/PG-buckup-tgbot/.env
ExecStart=/path/to/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable pg-backup-bot
sudo systemctl start pg-backup-bot
sudo systemctl status pg-backup-bot
```

---

## 📝 Зависимости

### requirements.txt
- `python-telegram-bot[job-queue]==21.10` — Telegram Bot API + планировщик
- `python-dotenv==1.0.1` — загрузка `.env`

### Docker-образ
- `python:3.12-slim-bookworm`
- `postgresql-client-{version}` из PGDG repo (настраивается через `PG_CLIENT_VERSIONS`)

---

## 🔒 Безопасность

- ✅ Доступ только для пользователей из `ADMIN_IDS`
- ✅ Валидация имён backup-файлов (защита от path traversal)
- ✅ `.env` исключён из git
- ✅ Проверка backup через `pg_restore -l` перед сохранением
- ✅ Блокировка параллельных backup (asyncio.Lock)

---

## 🆘 Поддержка

При возникновении проблем:

1. Проверьте логи: `docker compose logs -f` или файл из `LOG_FILE`
2. Убедитесь, что `pg_dump` для нужной версии PG установлен (раздел «Базы данных» в меню)
3. Проверьте подключение к PostgreSQL (`PGHOST`, `PGPORT`, `PGPASSWORD`, `USE_SUDO`)
4. Для уведомлений: добавьте бота в чат, отправьте `/start`, получите ID через `/chatid`
5. После изменения `.env` перезапустите бота

### Частые ошибки

| Ошибка | Решение |
|---|---|
| `pg_dump не найден` | Добавьте версию в `PG_CLIENT_VERSIONS` и пересоберите образ |
| `chat not found` | Добавьте бота в чат, отправьте `/start`, обновите `BACKUP_CHAT_ID` |
| `pg_dump failed: connection refused` | Проверьте `PGHOST`/`PGPORT`, в Docker используйте `127.0.0.1` |
| `bot must be run as root` | Запустите от root или установите `USE_SUDO=false` |

---

## 📄 Лицензия

Проект разработан для личного использования.

---

## 👨‍💻 Разработчик

**Dev by witrix**
