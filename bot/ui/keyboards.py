from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.backup import BackupService
from bot.config import DatabaseConfig, Settings

PAGE_SIZE = 5


@dataclass
class BackupState:
    last_backup_at: datetime | None = None
    last_backup_status: str = "Ещё не выполнялся"
    is_running: bool = False
    current_task: str = ""


def back_button(callback: str = "menu") -> InlineKeyboardButton:
    return InlineKeyboardButton("◀️ Назад", callback_data=callback)


def main_menu_keyboard(state: BackupState) -> InlineKeyboardMarkup:
    backup_label = "⏳ Backup выполняется..." if state.is_running else "💾 Создать backup"
    backup_callback = "noop" if state.is_running else "screen:backup"

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(backup_label, callback_data=backup_callback)],
            [
                InlineKeyboardButton("🗄 Базы данных", callback_data="screen:databases"),
                InlineKeyboardButton("📁 История", callback_data="history:0"),
            ],
            [
                InlineKeyboardButton("📊 Статус", callback_data="screen:status"),
                InlineKeyboardButton("⚙️ Настройки", callback_data="screen:settings"),
            ],
            [InlineKeyboardButton("❓ Справка", callback_data="screen:help")],
        ]
    )


def backup_menu_keyboard(settings: Settings, state: BackupState) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    if not state.is_running:
        rows.append([InlineKeyboardButton("🚀 Backup всех баз", callback_data="confirm:all")])
        for db in settings.databases:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"📦 {db.name}",
                        callback_data=f"confirm:one:{db.name}",
                    )
                ]
            )

    rows.append([back_button()])
    return InlineKeyboardMarkup(rows)


def confirm_keyboard(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data=f"run:{action}"),
                InlineKeyboardButton("❌ Отмена", callback_data="screen:backup"),
            ]
        ]
    )


def database_detail_keyboard(db_name: str, state: BackupState) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if not state.is_running:
        rows.append([InlineKeyboardButton("💾 Сделать backup", callback_data=f"confirm:one:{db_name}")])
    rows.append(
        [
            back_button("screen:databases"),
            InlineKeyboardButton("🏠 Меню", callback_data="menu"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def databases_keyboard(settings: Settings) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"{'🟢' if settings.pg_dump_path(db.postgres_version).is_file() else '🔴'} {db.name}",
                callback_data=f"database:{db.name}",
            )
        ]
        for db in settings.databases
    ]
    rows.append([back_button()])
    return InlineKeyboardMarkup(rows)


def history_keyboard(
    files: list[Path],
    page: int,
    total_pages: int,
    backup_service: BackupService,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for file_path in files:
        size = backup_service.format_size(file_path.stat().st_size)
        label = f"📄 {file_path.name[:28]}…" if len(file_path.name) > 31 else f"📄 {file_path.name}"
        rows.append(
            [
                InlineKeyboardButton(label, callback_data=f"history:view:{page}:{file_path.name}"),
            ]
        )

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"history:{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"history:{page + 1}"))

    if nav:
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton("🔄 Обновить", callback_data=f"history:{page}"),
            back_button(),
        ]
    )
    return InlineKeyboardMarkup(rows)


def history_file_keyboard(page: int, filename: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📤 Отправить в чат", callback_data=f"history:send:{page}:{filename}"),
            ],
            [
                InlineKeyboardButton("◀️ К списку", callback_data=f"history:{page}"),
                InlineKeyboardButton("🏠 Меню", callback_data="menu"),
            ],
        ]
    )


def status_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 Обновить", callback_data="screen:status"),
                InlineKeyboardButton("📁 История", callback_data="history:0"),
            ],
            [back_button()],
        ]
    )


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[back_button()]])


def help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💾 Backup", callback_data="help:backup"),
                InlineKeyboardButton("🗄 Базы", callback_data="help:databases"),
            ],
            [
                InlineKeyboardButton("⏰ Расписание", callback_data="help:schedule"),
                InlineKeyboardButton("🐳 Docker", callback_data="help:docker"),
            ],
            [back_button()],
        ]
    )


def help_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("◀️ К справке", callback_data="screen:help")],
            [InlineKeyboardButton("🏠 Меню", callback_data="menu")],
        ]
    )
