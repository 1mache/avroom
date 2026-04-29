from __future__ import annotations

"""Central logging configuration for the FastAPI app.

Exposes a single `setup_logging()` function that wires both stdout and a
rotating file handler under `fastApi-app/logs/app.log`, and unifies uvicorn's
own loggers onto the same handlers so that all output shares one format.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


_LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
_LOG_FILE_MAX_BYTES: int = 5_000_000
_LOG_FILE_BACKUP_COUNT: int = 3
_DEFAULT_LEVEL: str = "INFO"
_UVICORN_LOGGERS: tuple[str, ...] = ("uvicorn", "uvicorn.access", "uvicorn.error")
# Loggers clamped to a fixed level regardless of the app's configured level.
# watchfiles spams a line per log-file write under --reload (feedback loop).
# uvicorn.access logs every HTTP request — too noisy for normal operation.
_CLAMPED_LOGGERS: dict[str, int] = {
    "watchfiles": logging.WARNING,
    "watchfiles.main": logging.WARNING,
    "uvicorn": logging.WARNING,
    "uvicorn.access": logging.ERROR,
    "uvicorn.error": logging.WARNING,
}


def _logs_dir() -> Path:
    """Return the directory used to store log files (sibling of `main.py`)."""

    return Path(__file__).resolve().parent / "logs"


def setup_logging(level: str | None = None) -> None:
    """Configure root + uvicorn loggers with shared stdout and rotating file handlers.

    The level is resolved from the `level` argument, falling back to the
    `LOG_LEVEL` environment variable, then to `INFO`.

    Idempotent: existing handlers on the root and uvicorn loggers are removed
    before new ones are attached, so reloads (e.g. `uvicorn --reload`) do not
    accumulate duplicate handlers that would print every line multiple times.
    """

    resolved_level: str = (level or os.environ.get("LOG_LEVEL") or _DEFAULT_LEVEL).upper()
    numeric_level: int = logging.getLevelNamesMapping().get(resolved_level, logging.INFO)

    logs_dir: Path = _logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file_path: Path = logs_dir / "app.log"

    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(numeric_level)

    file_handler = RotatingFileHandler(
        filename=log_file_path,
        maxBytes=_LOG_FILE_MAX_BYTES,
        backupCount=_LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(numeric_level)

    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        handler.close()
    root_logger.setLevel(numeric_level)
    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)

    # Route uvicorn's own loggers through the same handlers so HTTP and app
    # logs share one format. `propagate=False` prevents the root logger from
    # printing them a second time.
    for name in _UVICORN_LOGGERS:
        uv_logger = logging.getLogger(name)
        for handler in list(uv_logger.handlers):
            uv_logger.removeHandler(handler)
            handler.close()
        uv_logger.setLevel(_CLAMPED_LOGGERS.get(name, numeric_level))
        uv_logger.addHandler(stream_handler)
        uv_logger.addHandler(file_handler)
        uv_logger.propagate = False

    # Apply level clamps to any remaining noisy third-party loggers.
    for name, clamped_level in _CLAMPED_LOGGERS.items():
        if name not in _UVICORN_LOGGERS:
            logging.getLogger(name).setLevel(clamped_level)
