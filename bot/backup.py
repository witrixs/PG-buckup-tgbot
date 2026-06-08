from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from bot.config import DatabaseConfig, Settings
from bot.storage import cleanup_backups

logger = logging.getLogger(__name__)


class BackupError(Exception):
    pass


@dataclass(frozen=True)
class BackupResult:
    database: DatabaseConfig
    file_path: Path
    size_bytes: int


@dataclass(frozen=True)
class BackupFileInfo:
    path: Path
    size_bytes: int
    modified_at: datetime


class BackupService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @staticmethod
    def _timestamp() -> str:
        return datetime.now().strftime("%d.%m.%Y_%H-%M")

    def _backup_filename(self, db_name: str, timestamp: str | None = None) -> str:
        ts = timestamp or self._timestamp()
        return f"{db_name}_{ts}.backup"

    def _validate_tools(self, version: str) -> tuple[Path, Path]:
        pg_dump = self.settings.pg_dump_path(version)
        pg_restore = self.settings.pg_restore_path(version)

        if not pg_dump.is_file() or not os.access(pg_dump, os.X_OK):
            installed = ", ".join(self.list_installed_versions()) or "нет"
            raise BackupError(
                f"pg_dump для PostgreSQL {version} не найден: {pg_dump}\n"
                f"Установлены версии: {installed}\n"
                f"Проверьте DATABASES в .env и PG_CLIENT_VERSIONS в docker-compose.yml"
            )
        if not pg_restore.is_file() or not os.access(pg_restore, os.X_OK):
            raise BackupError(f"pg_restore not found or not executable: {pg_restore}")

        return pg_dump, pg_restore

    def list_installed_versions(self) -> list[str]:
        base = self.settings.postgres_bin_base
        if not base.is_dir():
            return []

        versions: list[str] = []
        for path in sorted(base.iterdir()):
            pg_dump = path / "bin" / "pg_dump"
            if path.is_dir() and pg_dump.is_file() and os.access(pg_dump, os.X_OK):
                versions.append(path.name)
        return versions

    def validate_configuration(self) -> None:
        missing: list[str] = []
        for database in self.settings.databases:
            pg_dump = self.settings.pg_dump_path(database.postgres_version)
            if not pg_dump.is_file():
                missing.append(f"{database.name} → PostgreSQL {database.postgres_version}")

        if missing:
            installed = ", ".join(self.list_installed_versions()) or "нет"
            configured = ", ".join(
                f"PG {db.postgres_version}" for db in self.settings.databases
            )
            raise BackupError(
                "Не найден pg_dump для настроенных версий PostgreSQL:\n"
                + "\n".join(f"  • {item}" for item in missing)
                + f"\n\nВ контейнере установлено: {installed}\n"
                f"В .env указано: {configured}\n"
                "Исправьте DATABASES в .env или PG_CLIENT_VERSIONS в docker-compose.yml"
            )

    def _build_dump_command(self, pg_dump: Path, db_name: str) -> list[str]:
        cmd = [str(pg_dump), "-Fc", "-b", "-v"]

        if self.settings.pg_host:
            cmd.extend(["-h", self.settings.pg_host])
        if self.settings.pg_port:
            cmd.extend(["-p", self.settings.pg_port])
        if self.settings.postgres_user:
            cmd.extend(["-U", self.settings.postgres_user])

        cmd.append(db_name)

        if self.settings.use_sudo and shutil.which("sudo"):
            return ["sudo", "-u", self.settings.postgres_user, *cmd]
        if self.settings.use_sudo:
            logger.warning("USE_SUDO=true, but sudo not found — running pg_dump directly")
        return cmd

    def _subprocess_env(self) -> dict[str, str] | None:
        if not self.settings.pg_password:
            return None
        env = os.environ.copy()
        env["PGPASSWORD"] = self.settings.pg_password
        return env

    def check_backup(self, backup_file: Path, postgres_version: str) -> None:
        _, pg_restore = self._validate_tools(postgres_version)

        if not backup_file.is_file():
            raise BackupError(f"Backup file does not exist: {backup_file}")
        if backup_file.stat().st_size == 0:
            raise BackupError(f"Backup file is empty: {backup_file}")

        cmd = [str(pg_restore), "-l", str(backup_file)]
        logger.info("Checking backup with: %s", " ".join(cmd))

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "unknown error").strip()
            raise BackupError(f"pg_restore -l failed for {backup_file.name}: {stderr}")

    def backup_database(
        self,
        database: DatabaseConfig,
        timestamp: str | None = None,
    ) -> BackupResult:
        self.settings.backup_dir.mkdir(parents=True, exist_ok=True)

        pg_dump, pg_restore = self._validate_tools(database.postgres_version)
        backup_file = self.settings.backup_dir / self._backup_filename(database.name, timestamp)

        cmd = self._build_dump_command(pg_dump, database.name)
        logger.info("Starting backup for %s (PostgreSQL %s)", database.name, database.postgres_version)
        logger.info("Command: %s > %s", " ".join(cmd), backup_file)

        with backup_file.open("wb") as output:
            result = subprocess.run(
                cmd,
                stdout=output,
                stderr=subprocess.PIPE,
                env=self._subprocess_env(),
            )

        if result.returncode != 0:
            backup_file.unlink(missing_ok=True)
            stderr = (result.stderr or b"unknown error").decode("utf-8", errors="replace").strip()
            raise BackupError(f"pg_dump failed for {database.name}: {stderr}")

        size_bytes = backup_file.stat().st_size
        logger.info("Backup created: %s (%s bytes)", backup_file, size_bytes)

        self.check_backup(backup_file, database.postgres_version)

        removed = cleanup_backups(self.settings.backup_dir, self.settings.backup_max_bytes)
        if removed:
            logger.info("Backup storage cleanup removed %s file(s)", len(removed))

        return BackupResult(database=database, file_path=backup_file, size_bytes=size_bytes)

    def backup_all(self, timestamp: str | None = None) -> list[BackupResult]:
        ts = timestamp or self._timestamp()
        results: list[BackupResult] = []

        for database in self.settings.databases:
            results.append(self.backup_database(database, timestamp=ts))

        return results

    @staticmethod
    def format_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        if size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    def get_database(self, name: str) -> DatabaseConfig | None:
        for database in self.settings.databases:
            if database.name == name:
                return database
        return None

    def _all_backup_files(self, db_name: str | None = None) -> list[Path]:
        if not self.settings.backup_dir.is_dir():
            return []

        files = [path for path in self.settings.backup_dir.glob("*.backup") if path.is_file()]
        if db_name:
            files = [path for path in files if path.name.startswith(f"{db_name}_")]
        files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return files

    def list_backups_paginated(
        self,
        page: int = 0,
        per_page: int = 5,
        db_name: str | None = None,
    ) -> tuple[list[Path], int, int]:
        files = self._all_backup_files(db_name)
        total_count = len(files)
        if total_count == 0:
            return [], 1, 0

        total_pages = (total_count + per_page - 1) // per_page
        page = max(0, min(page, total_pages - 1))
        start = page * per_page
        return files[start : start + per_page], total_pages, total_count

    def list_backups(self, db_name: str | None = None, limit: int = 5) -> list[BackupFileInfo]:
        return [
            BackupFileInfo(
                path=path,
                size_bytes=path.stat().st_size,
                modified_at=datetime.fromtimestamp(path.stat().st_mtime),
            )
            for path in self._all_backup_files(db_name)[:limit]
        ]

    def get_backup_file(self, filename: str) -> Path | None:
        if ".." in filename or "/" in filename or "\\" in filename:
            return None
        if not filename.endswith(".backup"):
            return None

        file_path = (self.settings.backup_dir / filename).resolve()
        backup_dir = self.settings.backup_dir.resolve()
        if not str(file_path).startswith(str(backup_dir)):
            return None
        if not file_path.is_file():
            return None
        return file_path

    def storage_stats(self) -> tuple[int, int]:
        files = self._all_backup_files()
        total_size = sum(path.stat().st_size for path in files)
        return len(files), total_size

    @staticmethod
    def hostname() -> str:
        return socket.gethostname()
