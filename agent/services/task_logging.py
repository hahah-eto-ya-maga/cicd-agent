import logging
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class SecretFormatter(logging.Formatter):
    converter = time.gmtime

    def __init__(self):
        super().__init__(
            "%(asctime)s.%(msecs)03dZ %(levelname)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        self.secrets = tuple(filter(None, (
            os.getenv(name) for name in (
                "GITHUB_TOKEN", "OPENAI_API_KEY", "GITHUB_WEBHOOK_SECRET",
                "PGPASSWORD", "POSTGRES_PASSWORD",
            )
        )))

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        for secret in self.secrets:
            text = text.replace(secret, "***")
        return text


@contextmanager
def task_logging(directory: Path, attempt: int = 1):
    """Отдельный файл на запуск задания, с копией вывода в stdout контейнера."""
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"attempt-{attempt}_{stamp}_{uuid4().hex[:8]}"
    path = directory / f"{run_id}.log"

    # Локальный logger не меняет обработчики других сессий и не остаётся
    # в глобальном реестре logging после завершения задания.
    logger = logging.Logger(f"task.{run_id}", level=logging.INFO)
    logger.propagate = False
    file_handler = logging.FileHandler(path, mode="x", encoding="utf-8")
    console_handler = logging.StreamHandler(sys.stdout)
    formatter = SecretFormatter()
    for handler in (file_handler, console_handler):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    try:
        yield logger
    finally:
        for handler in (file_handler, console_handler):
            logger.removeHandler(handler)
            handler.close()
