from __future__ import annotations

from datetime import datetime
from pathlib import Path

from bot.backup import BackupService
from bot.config import DatabaseConfig, Settings
from bot.ui.keyboards import BackupState


def _separator() -> str:
    return "━━━━━━━━━━━━━━━━━━━━"


def _now_str() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")


def main_menu_text(settings: Settings, state: BackupState) -> str:
    db_count = len(settings.databases)
    schedule = (
        f"🟢 {settings.schedule_hour:02d}:{settings.schedule_minute:02d} ({settings.timezone})"
        if settings.schedule_enabled
        else "🔴 выключено"
    )
    running = "🔄 <b>Идёт backup...</b>\n" if state.is_running else ""
    task = f"📌 {state.current_task}\n\n" if state.is_running and state.current_task else ""

    return (
        f"🛡 <b>PostgreSQL Backup Bot</b>\n"
        f"{_separator()}\n\n"
        f"{running}{task}"
        f"🖥 <b>Хост:</b> <code>{BackupService.hostname()}</code>\n"
        f"🗄 <b>Баз данных:</b> {db_count}\n"
        f"⏰ <b>Расписание:</b> {schedule}\n"
        f"📋 <b>Последний backup:</b> {state.last_backup_status}\n\n"
        f"Выберите действие 👇"
    )


def backup_menu_text(settings: Settings) -> str:
    db_lines = "\n".join(
        f"  • <code>{db.name}</code> — PostgreSQL {db.postgres_version}"
        for db in settings.databases
    )
    return (
        f"💾 <b>Создание backup</b>\n"
        f"{_separator()}\n\n"
        f"Будет выполнен <code>pg_dump -Fc -b -v</code>\n"
        f"Файлы сохраняются в <code>{settings.backup_dir}</code>\n\n"
        f"<b>Доступные базы:</b>\n{db_lines}\n\n"
        f"Выберите, что backup-ить 👇"
    )


def confirm_text(action: str, settings: Settings, db_name: str | None = None) -> str:
    if action == "all":
        names = ", ".join(f"<code>{db.name}</code>" for db in settings.databases)
        target = f"все базы ({names})"
    else:
        db = settings.databases[0] if db_name is None else next(
            (d for d in settings.databases if d.name == db_name), None
        )
        version = db.postgres_version if db else "?"
        target = f"<code>{db_name}</code> (PostgreSQL {version})"

    return (
        f"⚠️ <b>Подтверждение backup</b>\n"
        f"{_separator()}\n\n"
        f"Вы собираетесь создать backup:\n"
        f"▸ {target}\n\n"
        f"📂 Папка: <code>{settings.backup_dir}</code>\n"
        f"🕐 Время: {_now_str()}\n\n"
        f"Продолжить?"
    )


def databases_text(settings: Settings) -> str:
    lines = []
    for index, db in enumerate(settings.databases, start=1):
        ok = settings.pg_dump_path(db.postgres_version).is_file()
        icon = "🟢" if ok else "🔴"
        status = "готов" if ok else "pg_dump не найден"
        lines.append(
            f"{index}. {icon} <b>{db.name}</b>\n"
            f"   └ PG {db.postgres_version} · {status}"
        )

    return (
        f"🗄 <b>Базы данных</b>\n"
        f"{_separator()}\n\n"
        + "\n\n".join(lines)
        + "\n\n"
        "Нажмите на базу для подробностей 👇"
    )


def database_detail_text(settings: Settings, database: DatabaseConfig) -> str:
    pg_dump = settings.pg_dump_path(database.postgres_version)
    pg_restore = settings.pg_restore_path(database.postgres_version)
    dump_ok = "🟢 OK" if pg_dump.is_file() else "🔴 не найден"
    restore_ok = "🟢 OK" if pg_restore.is_file() else "🔴 не найден"

    backups = BackupService(settings).list_backups(database.name, limit=3)
    if backups:
        history_lines = "\n".join(
            f"  • {item.path.name} ({BackupService.format_size(item.size_bytes)})"
            for item in backups
        )
    else:
        history_lines = "  • пока нет backup-файлов"

    return (
        f"🗄 <b>{database.name}</b>\n"
        f"{_separator()}\n\n"
        f"🐘 <b>PostgreSQL:</b> {database.postgres_version}\n"
        f"📥 <b>pg_dump:</b> {dump_ok}\n"
        f"📤 <b>pg_restore:</b> {restore_ok}\n\n"
        f"📁 <b>Последние backup:</b>\n{history_lines}"
    )


def status_text(settings: Settings, state: BackupState) -> str:
    schedule = "🔴 выключено"
    if settings.schedule_enabled:
        schedule = f"🟢 ежедневно в {settings.schedule_hour:02d}:{settings.schedule_minute:02d} ({settings.timezone})"

    backup_service = BackupService(settings)
    total_files, total_size = backup_service.storage_stats()
    running = "🔄 Выполняется\n" if state.is_running else "💤 Ожидание\n"

    db_lines = "\n".join(
        f"  • <code>{db.name}</code> — PG {db.postgres_version}"
        for db in settings.databases
    )

    return (
        f"📊 <b>Статус системы</b>\n"
        f"{_separator()}\n\n"
        f"🖥 <b>Хост:</b> <code>{BackupService.hostname()}</code>\n"
        f"⚡ <b>Состояние:</b> {running}"
        f"📋 <b>Последний backup:</b> {state.last_backup_status}\n"
        f"⏰ <b>Расписание:</b> {schedule}\n\n"
        f"📂 <b>Хранилище</b>\n"
        f"  • Файлов: {total_files}\n"
        f"  • Общий размер: {BackupService.format_size(total_size)}\n"
        f"  • Путь: <code>{settings.backup_dir}</code>\n\n"
        f"🗄 <b>Базы:</b>\n{db_lines}"
    )


def settings_text(settings: Settings) -> str:
    pg_auth = "🔐 пароль" if settings.pg_password else "🔓 peer/trust"
    sudo = "✅ да" if settings.use_sudo else "❌ нет"
    backup_limit = (
        f"{settings.backup_max_bytes / 1024**3:.1f} GB"
        if settings.backup_max_bytes
        else "без лимита"
    )
    log_limit = (
        f"{settings.log_max_bytes / 1024**3:.1f} GB"
        if settings.log_max_bytes
        else "без лимита"
    )

    return (
        f"⚙️ <b>Настройки</b>\n"
        f"{_separator()}\n\n"
        f"📂 Backup: <code>{settings.backup_dir}</code>\n"
        f"📝 Лог: <code>{settings.log_file}</code>\n"
        f"💬 Чат backup: <code>{settings.backup_chat_id}</code>\n"
        f"👤 Админов: {len(settings.admin_ids)}\n\n"
        f"💾 <b>Лимиты хранилища</b>\n"
        f"  • Backup: {backup_limit}\n"
        f"  • Логи: {log_limit}\n\n"
        f"🐘 <b>PostgreSQL</b>\n"
        f"  • Bin: <code>{settings.postgres_bin_base}</code>\n"
        f"  • User: <code>{settings.postgres_user}</code>\n"
        f"  • Host: <code>{settings.pg_host or 'default'}</code>\n"
        f"  • Port: <code>{settings.pg_port or 'default'}</code>\n"
        f"  • Auth: {pg_auth}\n"
        f"  • Sudo: {sudo}\n\n"
        f"⏰ <b>Расписание</b>\n"
        f"  • {'Включено' if settings.schedule_enabled else 'Выключено'}\n"
        f"  • {settings.schedule_hour:02d}:{settings.schedule_minute:02d} ({settings.timezone})\n\n"
        f"<i>Настройки меняются в файле .env</i>"
    )


def history_text(files: list[Path], page: int, total_pages: int, total_count: int, backup_service: BackupService) -> str:
    if not files:
        return (
            f"📁 <b>История backup</b>\n"
            f"{_separator()}\n\n"
            f"📭 Backup-файлов пока нет.\n\n"
            f"Создайте первый backup через меню 💾"
        )

    lines = []
    for index, file_path in enumerate(files, start=page * 5 + 1):
        mtime = datetime.fromtimestamp(file_path.stat().st_mtime).strftime("%d.%m.%Y %H:%M")
        size = backup_service.format_size(file_path.stat().st_size)
        lines.append(f"{index}. <code>{file_path.name}</code>\n   └ {size} · {mtime}")

    return (
        f"📁 <b>История backup</b>\n"
        f"{_separator()}\n\n"
        f"Всего файлов: <b>{total_count}</b>\n"
        f"Страница: <b>{page + 1}</b> из <b>{total_pages}</b>\n\n"
        + "\n\n".join(lines)
        + "\n\n"
        "Нажмите на файл для подробностей 👇"
    )


def history_file_text(file_path: Path, backup_service: BackupService) -> str:
    stat = file_path.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%d.%m.%Y %H:%M:%S")
    size = backup_service.format_size(stat.st_size)

    parts = file_path.stem.split("_")
    db_guess = parts[0] if parts else "—"

    return (
        f"📄 <b>Backup-файл</b>\n"
        f"{_separator()}\n\n"
        f"📛 <b>Имя:</b>\n<code>{file_path.name}</code>\n\n"
        f"🗄 <b>База:</b> <code>{db_guess}</code>\n"
        f"📦 <b>Размер:</b> {size}\n"
        f"🕐 <b>Создан:</b> {mtime}\n"
        f"📂 <b>Путь:</b>\n<code>{file_path}</code>"
    )


def help_text() -> str:
    return (
        f"❓ <b>Справка</b>\n"
        f"{_separator()}\n\n"
        f"Выберите раздел, чтобы узнать подробнее 👇\n\n"
        f"💾 <b>Backup</b> — как создавать резервные копии\n"
        f"🗄 <b>Базы</b> — настройка баз данных\n"
        f"⏰ <b>Расписание</b> — автоматический backup\n"
        f"🐳 <b>Docker</b> — запуск в контейнере"
    )


def help_section_text(section: str) -> str:
    sections = {
        "backup": (
            f"💾 <b>Backup</b>\n{_separator()}\n\n"
            "1. Меню → <b>Создать backup</b>\n"
            "2. Выберите все базы или одну\n"
            "3. Подтвердите действие\n\n"
            "Формат: <code>pg_dump -Fc -b -v</code>\n"
            "Имя файла: <code>db_ДД.ММ.ГГГГ_ЧЧ-ММ.backup</code>\n\n"
            "Файлы отправляются в чат и сохраняются на сервере."
        ),
        "databases": (
            f"🗄 <b>Базы данных</b>\n{_separator()}\n\n"
            "Настройка в <code>.env</code>:\n"
            "<code>DATABASES=vetavpn_db:18,pasarguardveta_db:18</code>\n\n"
            "Формат: <code>имя:версия_postgres</code>\n"
            "Для каждой базы можно указать свою версию PG."
        ),
        "schedule": (
            f"⏰ <b>Расписание</b>\n{_separator()}\n\n"
            "<code>SCHEDULE_ENABLED=true</code>\n"
            "<code>SCHEDULE_HOUR=3</code>\n"
            "<code>SCHEDULE_MINUTE=0</code>\n"
            "<code>TIMEZONE=Europe/Moscow</code>\n\n"
            "Backup отправляется в чат <code>BACKUP_CHAT_ID</code>."
        ),
        "docker": (
            f"🐳 <b>Docker</b>\n{_separator()}\n\n"
            "<code>docker compose up -d --build</code>\n"
            "<code>docker compose logs -f</code>\n\n"
            "После изменения <code>.env</code>:\n"
            "<code>docker compose up -d --build</code>"
        ),
    }
    return sections.get(section, help_text())


def backup_started_text(db_names: list[str]) -> str:
    names = "\n".join(f"  ▸ <code>{name}</code>" for name in db_names)
    return (
        f"🔄 <b>Backup запущен</b>\n"
        f"{_separator()}\n\n"
        f"🖥 {BackupService.hostname()}\n"
        f"🕐 {_now_str()}\n\n"
        f"<b>Базы:</b>\n{names}"
    )


def backup_progress_text(
    db_names: list[str],
    completed: list[str],
    current: str | None,
) -> str:
    total = len(db_names)
    done = len(completed)
    bar_filled = int((done / total) * 10) if total else 0
    bar = "▓" * bar_filled + "░" * (10 - bar_filled)

    lines = []
    for name in db_names:
        if name in completed:
            lines.append(f"  ✅ <code>{name}</code>")
        elif name == current:
            lines.append(f"  ⏳ <code>{name}</code> ...")
        else:
            lines.append(f"  ⬜ <code>{name}</code>")

    return (
        f"🔄 <b>Backup в процессе</b>\n"
        f"{_separator()}\n\n"
        f"[{bar}] {done}/{total}\n\n"
        + "\n".join(lines)
    )


def backup_success_text(results: list, duration: float, backup_dir: Path) -> str:
    files_list = "\n".join(
        f"  • <code>{item.file_path.name}</code> ({BackupService.format_size(item.size_bytes)})"
        for item in results
    )
    return (
        f"✅ <b>Backup завершён</b>\n"
        f"{_separator()}\n\n"
        f"🖥 {BackupService.hostname()}\n"
        f"🕐 {_now_str()}\n"
        f"⏱ {duration:.1f} сек\n\n"
        f"<b>Файлы:</b>\n{files_list}\n\n"
        f"📂 <code>{backup_dir}</code>"
    )


def backup_error_text(error: str) -> str:
    return (
        f"❌ <b>Ошибка backup</b>\n"
        f"{_separator()}\n\n"
        f"🖥 {BackupService.hostname()}\n"
        f"🕐 {_now_str()}\n\n"
        f"<code>{error}</code>"
    )


def startup_ready_text(settings: Settings) -> str:
    schedule = (
        f"🟢 ежедневно в {settings.schedule_hour:02d}:{settings.schedule_minute:02d} ({settings.timezone})"
        if settings.schedule_enabled
        else "🔴 выключено"
    )
    db_lines = "\n".join(
        f"  • <code>{db.name}</code> — PostgreSQL {db.postgres_version}"
        for db in settings.databases
    )
    backup_limit = (
        f"{settings.backup_max_bytes / 1024**3:.1f} GB"
        if settings.backup_max_bytes
        else "без лимита"
    )

    return (
        f"🟢 <b>Бот запущен и готов к работе</b>\n"
        f"{_separator()}\n\n"
        f"🖥 <b>Хост:</b> <code>{BackupService.hostname()}</code>\n"
        f"🕐 <b>Время:</b> {_now_str()}\n"
        f"⏰ <b>Расписание:</b> {schedule}\n"
        f"📂 <b>Backup:</b> <code>{settings.backup_dir}</code>\n"
        f"💾 <b>Лимит backup:</b> {backup_limit}\n\n"
        f"🗄 <b>Базы данных:</b>\n{db_lines}\n\n"
        f"Используйте /start для меню управления."
    )
