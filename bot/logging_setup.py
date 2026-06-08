from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_file: Path, log_max_bytes: int = 0) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    if log_max_bytes > 0:
        chunk_size = max(1024 * 1024, log_max_bytes // 5)
        file_handler: logging.Handler = RotatingFileHandler(
            log_file,
            maxBytes=chunk_size,
            backupCount=4,
            encoding="utf-8",
        )
    else:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")

    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
