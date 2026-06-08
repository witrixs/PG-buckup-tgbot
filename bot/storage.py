from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def directory_size(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(item.stat().st_size for item in directory.iterdir() if item.is_file())


def cleanup_directory(
    directory: Path,
    max_bytes: int,
    *,
    glob_pattern: str = "*",
) -> list[str]:
    """Удаляет самые старые файлы, пока размер папки не станет <= max_bytes."""
    if max_bytes <= 0 or not directory.is_dir():
        return []

    files = sorted(
        (item for item in directory.glob(glob_pattern) if item.is_file()),
        key=lambda item: item.stat().st_mtime,
    )

    deleted: list[str] = []
    total = directory_size(directory)

    while total > max_bytes and files:
        oldest = files.pop(0)
        file_size = oldest.stat().st_size
        oldest.unlink(missing_ok=True)
        total -= file_size
        deleted.append(oldest.name)
        logger.info(
            "Storage cleanup: deleted %s (%s bytes), dir %s: %s bytes left",
            oldest.name,
            file_size,
            directory,
            total,
        )

    return deleted


def cleanup_backups(backup_dir: Path, max_bytes: int) -> list[str]:
    return cleanup_directory(backup_dir, max_bytes, glob_pattern="*.backup")


def cleanup_logs(log_file: Path, max_bytes: int) -> list[str]:
    log_dir = log_file.parent
    if max_bytes <= 0:
        return []

    deleted = cleanup_directory(log_dir, max_bytes, glob_pattern="*.log*")

    if log_file.is_file() and directory_size(log_dir) > max_bytes:
        size = log_file.stat().st_size
        keep_bytes = max(256 * 1024, max_bytes // 2)
        if size > keep_bytes:
            with log_file.open("rb") as source:
                source.seek(-keep_bytes, 2)
                tail = source.read()
            with log_file.open("wb") as target:
                target.write(b"... [log truncated] ...\n")
                target.write(tail)
            logger.warning(
                "Log truncated: %s (%s -> ~%s bytes)",
                log_file.name,
                size,
                keep_bytes,
            )

    return deleted
