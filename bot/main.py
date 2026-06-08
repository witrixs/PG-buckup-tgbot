from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import Application

from bot.backup import BackupService
from bot.config import Settings, load_settings
from bot.handlers import register_handlers
from bot.logging_setup import setup_logging
from bot.scheduler import setup_scheduler
from bot.storage import cleanup_backups, cleanup_logs
from bot.ui.messages import startup_ready_text

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    load_dotenv(env_path)


def _check_root_if_required() -> None:
    use_sudo = os.getenv("USE_SUDO", "true").strip().lower() in {"1", "true", "yes", "on"}
    if use_sudo and os.geteuid() != 0:
        print("ERROR: bot must be run as root when USE_SUDO=true", file=sys.stderr)
        sys.exit(1)


def _list_pg_versions(settings: Settings) -> list[str]:
    base = settings.postgres_bin_base
    if not base.is_dir():
        return []

    versions: list[str] = []
    for path in sorted(base.iterdir()):
        pg_dump = path / "bin" / "pg_dump"
        if path.is_dir() and pg_dump.is_file():
            versions.append(path.name)
    return versions


def _validate_pg_tools(settings: Settings) -> None:
    missing: list[str] = []
    for database in settings.databases:
        pg_dump = settings.pg_dump_path(database.postgres_version)
        if not pg_dump.is_file():
            missing.append(f"{database.name} → PostgreSQL {database.postgres_version}")

    if not missing:
        return

    installed = ", ".join(_list_pg_versions(settings)) or "нет"
    configured = ", ".join(f"PG {db.postgres_version}" for db in settings.databases)
    logger.error(
        "Не найден pg_dump для настроенных версий PostgreSQL:\n"
        "  • %s\n\n"
        "В контейнере установлено: %s\n"
        "В .env указано: %s\n"
        "Исправьте DATABASES в .env или PG_CLIENT_VERSIONS в docker-compose.yml",
        "\n  • ".join(missing),
        installed,
        configured,
    )
    sys.exit(1)


async def _send_startup_message(application: Application) -> None:
    settings: Settings = application.bot_data["settings"]
    text = startup_ready_text(settings)
    sent_to: list[int] = []

    for chat_id in settings.notification_chat_ids():
        try:
            await application.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
            )
            sent_to.append(chat_id)
            logger.info("Startup notification sent to chat %s", chat_id)
        except BadRequest as exc:
            error = str(exc).lower()
            if "chat not found" in error:
                logger.warning(
                    "Startup notification skipped for chat %s: chat not found. "
                    "Add bot to this chat and send /start, or use /chatid to get correct ID.",
                    chat_id,
                )
            elif "bot was blocked" in error:
                logger.warning("Startup notification skipped for chat %s: bot was blocked", chat_id)
            else:
                logger.warning("Startup notification failed for chat %s: %s", chat_id, exc)
        except Exception:
            logger.exception("Startup notification failed for chat %s", chat_id)

    if not sent_to:
        logger.error(
            "Startup notification was not delivered. "
            "Send /start to the bot and set BACKUP_CHAT_ID using /chatid"
        )


def main() -> None:
    _load_env()
    settings = load_settings()

    cleanup_logs(settings.log_file, settings.log_max_bytes)
    setup_logging(settings.log_file, settings.log_max_bytes)

    logger.info("Environment loaded from %s", PROJECT_ROOT / ".env")
    if settings.pg_host:
        logger.info("PostgreSQL connection: %s:%s", settings.pg_host, settings.pg_port or "5432")
    if settings.backup_max_bytes:
        logger.info("Backup storage limit: %.2f GB", settings.backup_max_bytes / 1024**3)
    if settings.log_max_bytes:
        logger.info("Log storage limit: %.2f GB", settings.log_max_bytes / 1024**3)
    _check_root_if_required()

    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    removed = cleanup_backups(settings.backup_dir, settings.backup_max_bytes)
    if removed:
        logger.info("Startup backup cleanup removed %s file(s)", len(removed))

    backup_service = BackupService(settings)
    _validate_pg_tools(settings)

    logger.info(
        "PostgreSQL clients available: %s",
        ", ".join(_list_pg_versions(settings)) or "нет",
    )

    application = (
        Application.builder()
        .token(settings.bot_token)
        .post_init(_send_startup_message)
        .build()
    )

    application.bot_data["settings"] = settings
    application.bot_data["backup_service"] = backup_service

    register_handlers(application)
    setup_scheduler(application, settings)

    logger.info("Bot started. Databases: %s", ", ".join(db.name for db in settings.databases))
    logger.info("Backup directory: %s", settings.backup_dir)

    application.run_polling(drop_pending_updates=True)
    logger.info("Bot stopped")


if __name__ == "__main__":
    main()
