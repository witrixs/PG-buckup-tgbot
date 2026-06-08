from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatabaseConfig:
    name: str
    postgres_version: str = "18"


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    backup_chat_id: int
    backup_dir: Path
    log_file: Path
    postgres_bin_base: Path
    postgres_user: str
    pg_host: str | None
    pg_port: str | None
    pg_password: str | None
    use_sudo: bool
    schedule_enabled: bool
    schedule_hour: int
    schedule_minute: int
    databases: tuple[DatabaseConfig, ...]
    timezone: str
    backup_max_bytes: int
    log_max_bytes: int

    def pg_dump_path(self, version: str) -> Path:
        return self.postgres_bin_base / version / "bin" / "pg_dump"

    def pg_restore_path(self, version: str) -> Path:
        return self.postgres_bin_base / version / "bin" / "pg_restore"

    def notification_chat_ids(self) -> tuple[int, ...]:
        seen: set[int] = set()
        chat_ids: list[int] = []
        for chat_id in (self.backup_chat_id, *sorted(self.admin_ids)):
            if chat_id not in seen:
                chat_ids.append(chat_id)
                seen.add(chat_id)
        return tuple(chat_ids)


def _parse_admin_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            ids.add(int(part))
    if not ids:
        raise ValueError("ADMIN_IDS must contain at least one Telegram user id")
    return frozenset(ids)


def _parse_databases(raw: str) -> tuple[DatabaseConfig, ...]:
    raw = raw.strip()
    if not raw:
        raise ValueError("DATABASES is empty")

    if raw.startswith("["):
        items = json.loads(raw)
        databases = [
            DatabaseConfig(
                name=str(item["name"]),
                postgres_version=str(item.get("postgres_version", item.get("version", "18"))),
            )
            for item in items
        ]
    else:
        databases = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                name, version = part.split(":", 1)
                databases.append(DatabaseConfig(name=name.strip(), postgres_version=version.strip()))
            else:
                databases.append(DatabaseConfig(name=part))

    if not databases:
        raise ValueError("DATABASES must contain at least one database")
    return tuple(databases)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_pg_host(
    pg_host: str | None,
    pg_password: str | None,
    use_sudo: bool,
) -> str | None:
    """Docker не может использовать peer-auth через unix-socket — нужен TCP."""
    if pg_host and pg_host.startswith("/"):
        if not use_sudo:
            return "127.0.0.1"
        if pg_password:
            return "127.0.0.1"
        return pg_host

    if not pg_host and pg_password and not use_sudo:
        return "127.0.0.1"

    return pg_host


def _parse_size_gb(name: str, default: float) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        value = default
    else:
        value = float(raw)
    if value <= 0:
        return 0
    return int(value * 1024**3)


def load_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise ValueError("BOT_TOKEN is not set")

    admin_ids_raw = os.getenv("ADMIN_IDS", "").strip()
    if not admin_ids_raw:
        raise ValueError("ADMIN_IDS is not set")

    admin_ids = _parse_admin_ids(admin_ids_raw)

    backup_chat_id_raw = os.getenv("BACKUP_CHAT_ID", "").strip()
    if backup_chat_id_raw:
        backup_chat_id = int(backup_chat_id_raw)
    else:
        backup_chat_id = next(iter(admin_ids))

    databases_raw = os.getenv("DATABASES", "").strip()
    if not databases_raw:
        raise ValueError("DATABASES is not set")

    backup_dir = Path(os.getenv("BACKUP_DIR", "/root"))
    log_file = Path(os.getenv("LOG_FILE", "/var/log/pg_backup_telegram.log"))

    pg_host_raw = os.getenv("PGHOST", "").strip() or None
    pg_port = os.getenv("PGPORT", "").strip() or None
    pg_password = os.getenv("PGPASSWORD", "").strip() or None
    use_sudo = _env_bool("USE_SUDO", True)
    pg_host = _normalize_pg_host(pg_host_raw, pg_password, use_sudo)

    return Settings(
        bot_token=bot_token,
        admin_ids=admin_ids,
        backup_chat_id=backup_chat_id,
        backup_dir=backup_dir,
        log_file=log_file,
        postgres_bin_base=Path(os.getenv("POSTGRES_BIN_BASE", "/usr/lib/postgresql")),
        postgres_user=os.getenv("POSTGRES_USER", "postgres"),
        pg_host=pg_host,
        pg_port=pg_port,
        pg_password=pg_password,
        use_sudo=use_sudo,
        schedule_enabled=_env_bool("SCHEDULE_ENABLED", True),
        schedule_hour=int(os.getenv("SCHEDULE_HOUR", "3")),
        schedule_minute=int(os.getenv("SCHEDULE_MINUTE", "0")),
        databases=_parse_databases(databases_raw),
        timezone=os.getenv("TIMEZONE", "Europe/Moscow"),
        backup_max_bytes=_parse_size_gb("BACKUP_MAX_SIZE_GB", 1.0),
        log_max_bytes=_parse_size_gb("LOG_MAX_SIZE_GB", 1.0),
    )
