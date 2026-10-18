import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


DatabaseError = psycopg.Error


class Database:
    def __init__(self):
        self.pool = ConnectionPool(
            min_size=1,
            max_size=3,
            kwargs= {
                "connect_timeout": 5,
                "row_factory": dict_row
            }
        )

    def check_connection(self):
        with self.pool.connection() as conn:
            conn.execute("SELECT 1")

    def claim_next_task(self):
        with self.pool.connection() as conn:
            query = """
                UPDATE tasks
                SET status = 'running',
                    attempts = attempts + 1,
                    started_at = now()
                WHERE id = (
                    SELECT id
                    FROM tasks
                    WHERE status = 'queued'
                    ORDER BY created_at, id
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING *
            """

            return conn.execute(query).fetchone()

    def close(self):
        self.pool.close()

    # Здесь будут методы получения задания, сохранения результата и ошибки.
    # Каждый метод сам открывает соединение и выполняет свою транзакцию.
