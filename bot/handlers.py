from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from bot.backup import BackupError, BackupService
from bot.config import DatabaseConfig, Settings
from bot.storage import cleanup_backups
from bot.ui.keyboards import (
    PAGE_SIZE,
    BackupState,
    backup_menu_keyboard,
    confirm_keyboard,
    database_detail_keyboard,
    databases_keyboard,
    help_back_keyboard,
    help_keyboard,
    history_file_keyboard,
    history_keyboard,
    main_menu_keyboard,
    settings_keyboard,
    status_keyboard,
)
from bot.ui.messages import (
    backup_error_text,
    backup_menu_text,
    backup_progress_text,
    backup_started_text,
    backup_success_text,
    confirm_text,
    database_detail_text,
    databases_text,
    help_section_text,
    help_text,
    history_file_text,
    history_text,
    main_menu_text,
    settings_text,
    status_text,
)

logger = logging.getLogger(__name__)

BACKUP_LOCK = asyncio.Lock()
STATE = BackupState()


def _is_admin(update: Update, settings: Settings) -> bool:
    user = update.effective_user
    return user is not None and user.id in settings.admin_ids


async def _deny(update: Update) -> None:
    text = "⛔ <b>Доступ запрещён</b>\n\nУ вас нет прав для управления этим ботом."
    if update.callback_query and update.callback_query.message:
        await update.callback_query.message.edit_text(text, parse_mode=ParseMode.HTML)
    elif update.effective_message:
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)


async def _safe_edit(query, text: str, reply_markup) -> None:
    try:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    except BadRequest as exc:
        error = str(exc).lower()
        if "message is not modified" in error:
            return
        logger.warning("editMessageText failed: %s", exc)
        if query.message:
            await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def _show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, *, edit: bool = False) -> None:
    settings: Settings = context.bot_data["settings"]
    text = main_menu_text(settings, STATE)
    markup = main_menu_keyboard(STATE)

    if edit and update.callback_query and update.callback_query.message:
        await _safe_edit(update.callback_query, text, markup)
    elif update.effective_message:
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    elif update.callback_query and update.callback_query.message:
        await _safe_edit(update.callback_query, text, markup)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    if not _is_admin(update, settings):
        await _deny(update)
        return
    await _show_menu(update, context)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def _run_backup_job(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    databases: list[DatabaseConfig] | None = None,
    progress_message_id: int | None = None,
) -> None:
    settings: Settings = context.bot_data["settings"]
    backup_service: BackupService = context.bot_data["backup_service"]

    if BACKUP_LOCK.locked():
        await context.bot.send_message(
            chat_id=chat_id,
            text="⏳ Backup уже выполняется. Дождитесь завершения.",
        )
        return

    async with BACKUP_LOCK:
        started_at = datetime.now()
        target_databases = list(databases or settings.databases)
        db_names = [db.name for db in target_databases]

        STATE.is_running = True
        STATE.current_task = f"Backup: {', '.join(db_names)}"

        progress_id = progress_message_id
        if progress_id is None:
            progress_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=backup_started_text(db_names),
                parse_mode=ParseMode.HTML,
            )
            progress_id = progress_msg.message_id
        else:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_id,
                text=backup_started_text(db_names),
                parse_mode=ParseMode.HTML,
            )

        completed: list[str] = []
        results = []

        try:
            loop = asyncio.get_running_loop()
            timestamp = datetime.now().strftime("%d.%m.%Y_%H-%M")

            await loop.run_in_executor(
                None,
                cleanup_backups,
                settings.backup_dir,
                settings.backup_max_bytes,
            )

            for database in target_databases:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_id,
                    text=backup_progress_text(db_names, completed, database.name),
                    parse_mode=ParseMode.HTML,
                )

                result = await loop.run_in_executor(
                    None,
                    backup_service.backup_database,
                    database,
                    timestamp,
                )
                results.append(result)
                completed.append(database.name)

                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_id,
                    text=backup_progress_text(db_names, completed, None),
                    parse_mode=ParseMode.HTML,
                )

            for result in results:
                caption = (
                    f"📦 <b>{result.database.name}</b>\n"
                    f"PostgreSQL {result.database.postgres_version}\n"
                    f"📦 {backup_service.format_size(result.size_bytes)}"
                )
                with result.file_path.open("rb") as backup_file:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=backup_file,
                        filename=result.file_path.name,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                    )

            duration = (datetime.now() - started_at).total_seconds()
            STATE.last_backup_at = datetime.now()
            STATE.last_backup_status = f"✅ {STATE.last_backup_at.strftime('%d.%m.%Y %H:%M:%S')}"

            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_id,
                text=backup_success_text(results, duration, settings.backup_dir),
                parse_mode=ParseMode.HTML,
                reply_markup=main_menu_keyboard(STATE),
            )
            logger.info("Backup completed successfully for: %s", ", ".join(db_names))

        except (BackupError, Exception) as exc:
            STATE.last_backup_status = f"❌ {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
            logger.exception("Backup failed")
            error_text = backup_error_text(str(exc))
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_id,
                text=error_text,
                parse_mode=ParseMode.HTML,
                reply_markup=main_menu_keyboard(STATE),
            )
        finally:
            STATE.is_running = False
            STATE.current_task = ""


async def callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    backup_service: BackupService = context.bot_data["backup_service"]

    query = update.callback_query
    if query is None:
        return

    if not _is_admin(update, settings):
        await query.answer("Нет доступа", show_alert=True)
        await _deny(update)
        return

    data = query.data or ""

    if data == "noop":
        await query.answer("Backup уже выполняется" if STATE.is_running else "OK")
        return

    await query.answer()

    if data == "menu":
        await _safe_edit(query, main_menu_text(settings, STATE), main_menu_keyboard(STATE))
        return

    if data == "screen:backup":
        await _safe_edit(query, backup_menu_text(settings), backup_menu_keyboard(settings, STATE))
        return

    if data == "screen:databases":
        await _safe_edit(query, databases_text(settings), databases_keyboard(settings))
        return

    if data == "screen:status":
        await _safe_edit(query, status_text(settings, STATE), status_keyboard())
        return

    if data == "screen:settings":
        await _safe_edit(query, settings_text(settings), settings_keyboard())
        return

    if data == "screen:help":
        await _safe_edit(query, help_text(), help_keyboard())
        return

    if data.startswith("help:"):
        section = data.removeprefix("help:")
        await _safe_edit(query, help_section_text(section), help_back_keyboard())
        return

    if data.startswith("database:"):
        db_name = data.removeprefix("database:")
        database = backup_service.get_database(db_name)
        if database is None:
            await query.answer("База не найдена", show_alert=True)
            return
        await _safe_edit(
            query,
            database_detail_text(settings, database),
            database_detail_keyboard(db_name, STATE),
        )
        return

    if data == "confirm:all":
        await _safe_edit(query, confirm_text("all", settings), confirm_keyboard("all"))
        return

    if data.startswith("confirm:one:"):
        db_name = data.removeprefix("confirm:one:")
        if backup_service.get_database(db_name) is None:
            await query.answer("База не найдена", show_alert=True)
            return
        await _safe_edit(query, confirm_text("one", settings, db_name), confirm_keyboard(f"one:{db_name}"))
        return

    if data == "run:all":
        if query.message is None:
            return
        await _run_backup_job(context, query.message.chat_id, progress_message_id=query.message.message_id)
        return

    if data.startswith("run:one:"):
        db_name = data.removeprefix("run:one:")
        database = backup_service.get_database(db_name)
        if database is None or query.message is None:
            await query.answer("База не найдена", show_alert=True)
            return
        await _run_backup_job(
            context,
            query.message.chat_id,
            databases=[database],
            progress_message_id=query.message.message_id,
        )
        return

    if data.startswith("history:"):
        parts = data.split(":")
        action = parts[1]

        if action == "send" and len(parts) >= 4:
            page = int(parts[2])
            filename = ":".join(parts[3:])
            file_path = backup_service.get_backup_file(filename)
            if file_path is None:
                await query.answer("Файл не найден", show_alert=True)
                return
            with file_path.open("rb") as backup_file:
                await context.bot.send_document(
                    chat_id=query.message.chat_id,
                    document=backup_file,
                    filename=file_path.name,
                    caption=f"📤 <code>{file_path.name}</code>",
                    parse_mode=ParseMode.HTML,
                )
            await query.answer("Файл отправлен")
            return

        if action == "view" and len(parts) >= 4:
            page = int(parts[2])
            filename = ":".join(parts[3:])
            file_path = backup_service.get_backup_file(filename)
            if file_path is None:
                await query.answer("Файл не найден", show_alert=True)
                return
            await _safe_edit(
                query,
                history_file_text(file_path, backup_service),
                history_file_keyboard(page, filename),
            )
            return

        page = int(action)
        files, total_pages, total_count = backup_service.list_backups_paginated(page, PAGE_SIZE)
        await _safe_edit(
            query,
            history_text(files, page, total_pages, total_count, backup_service),
            history_keyboard(files, page, total_pages, backup_service),
        )
        return


async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    if not _is_admin(update, settings):
        await _deny(update)
        return
    if update.effective_chat is None:
        return
    await _run_backup_job(context, update.effective_chat.id)


async def backup_db_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    backup_service: BackupService = context.bot_data["backup_service"]

    if not _is_admin(update, settings):
        await _deny(update)
        return
    if not context.args or update.effective_chat is None:
        if update.effective_message:
            await update.effective_message.reply_text(
                "Используйте меню /start или:\n/backup_db vetavpn_db",
            )
        return

    database = backup_service.get_database(context.args[0])
    if database is None:
        if update.effective_message:
            await update.effective_message.reply_text(f"❌ База <code>{context.args[0]}</code> не найдена.", parse_mode=ParseMode.HTML)
        return

    await _run_backup_job(context, update.effective_chat.id, databases=[database])


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    if not _is_admin(update, settings):
        await _deny(update)
        return
    if update.effective_message:
        await update.effective_message.reply_text(help_text(), parse_mode=ParseMode.HTML, reply_markup=help_keyboard())


async def databases_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    if not _is_admin(update, settings):
        await _deny(update)
        return
    if update.effective_message:
        await update.effective_message.reply_text(
            databases_text(settings),
            parse_mode=ParseMode.HTML,
            reply_markup=databases_keyboard(settings),
        )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    if not _is_admin(update, settings):
        await _deny(update)
        return
    if update.effective_message:
        await update.effective_message.reply_text(
            status_text(settings, STATE),
            parse_mode=ParseMode.HTML,
            reply_markup=status_keyboard(),
        )


async def chatid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    if not _is_admin(update, settings):
        await _deny(update)
        return

    chat = update.effective_chat
    if chat is None or update.effective_message is None:
        return

    title = f"<b>{chat.title}</b>\n" if chat.title else ""
    username = f"@{chat.username}\n" if chat.username else ""

    await update.effective_message.reply_text(
        f"🆔 <b>ID этого чата</b>\n\n"
        f"{title}{username}"
        f"Тип: <code>{chat.type}</code>\n"
        f"Chat ID: <code>{chat.id}</code>\n\n"
        f"Скопируйте в <code>.env</code>:\n"
        f"<code>BACKUP_CHAT_ID=\"{chat.id}\"</code>",
        parse_mode=ParseMode.HTML,
    )


async def scheduled_backup(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    await _run_backup_job(context, settings.backup_chat_id)


def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("databases", databases_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("chatid", chatid_command))
    application.add_handler(CommandHandler("backup", backup_command))
    application.add_handler(CommandHandler("backup_db", backup_db_command))
    application.add_handler(CallbackQueryHandler(callback_query))
