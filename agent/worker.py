import time
from pathlib import Path

from openai import OpenAI

from DB import Database, DatabaseError, DatabaseTimeout
from agent_session import AgentSession


def worker_loop(db: Database, client: OpenAI, model: str):
    workspaces = Path("workspaces").resolve()
    while True:
        try:
            task = db.claim_next_task()
            
        except (DatabaseError, DatabaseTimeout) as error:
            print(f"Ошибка подключения к PostgreSQL: {error}")
            time.sleep(5)
            continue

        if task is None:
            time.sleep(2)
            continue

        try:
            workspace = workspaces / f"task-{task['id']}"
            workspace.mkdir(parents=True, exist_ok=True)

            # Здесь скачать repository в workspace на точном commit_sha.
            # Здесь скачать логи run_id / run_attempt и сохранить в ci.log.

            session = AgentSession(client=client, model=model, workdir=workspace)
            result = session.submit(
                f"Исправь падение CI в {task['repository']}. "
                f"Код находится в {workspace}. Логи находятся в ci.log. "
                "Найди причину, исправь код и запусти проверки."
            )

            # Здесь сохранить result и результаты проверок в PostgreSQL.
            # По результатам проверок определить итоговый статус задания.
        except Exception as error:
            print(f"Ошибка задания {task['id']}: {error}")
            # Здесь записать ошибку и статус failed в PostgreSQL.
