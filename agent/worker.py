import time
import logging

from openai import OpenAI

from services.database import Database, DatabaseError, DatabaseTimeout
from core.session import AgentSession
from services.repository_loader import RepositoryLoader
from services.task_logging import task_logging


logger = logging.getLogger(__name__)


def worker_loop(
    db: Database, client: OpenAI, model: str,
    loader: RepositoryLoader,
):
    while True:
        try:
            task = db.claim_next_task()
            
        except (DatabaseError, DatabaseTimeout) as error:
            logger.error("Ошибка подключения к PostgreSQL: %s", error)
            time.sleep(5)
            continue

        if task is None:
            time.sleep(2)
            continue

        try:
            log_dir = loader.logs_path(task["repository"], task["id"])
            with task_logging(log_dir, attempt=task.get("attempts", 1)) as task_logger:
                try:
                    task_logger.info(
                        "Начало задания %s: repository=%s commit=%s CI run=%s attempt=%s",
                        task["id"], task["repository"], task["commit_sha"],
                        task.get("run_id"), task.get("run_attempt"),
                    )
                    workspace = loader.prepare(task)
                    task_logger.info("Код и логи CI подготовлены: %s", workspace)

                    session = AgentSession(
                        client=client, model=model, workdir=workspace, logger=task_logger,
                    )
                    result = session.submit(
                        f"Исправь падение CI в {task['repository']}. "
                        f"Код находится в {workspace}. Логи находятся в ci.log. "
                        "Найди причину, исправь код и запусти проверки."
                    )
                    task_logger.info("Сессия задания %s завершена", task["id"])

                    # Здесь сохранить result и результаты проверок в PostgreSQL.
                    # По результатам проверок определить итоговый статус задания.
                except Exception:
                    task_logger.exception("Ошибка задания %s", task["id"])
                    # Здесь записать ошибку и статус failed в PostgreSQL.
                except KeyboardInterrupt:
                    task_logger.warning("Задание %s прервано", task["id"])
                    raise
        except Exception:
            logger.exception("Не удалось подготовить журнал задания %s", task["id"])
