import psycopg
from psycopg.rows import dict_row


DatabaseError = psycopg.Error


class Database:
    def _connect(self):
        # PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD приходят из Compose.
        # Использовать через with: транзакция завершается, соединение закрывается.
        return psycopg.connect(connect_timeout=5, row_factory=dict_row)

    def check_connection(self):
        with self._connect() as conn:
            conn.execute("SELECT 1")

    # Здесь будут методы получения задания, сохранения результата и ошибки.
    # Каждый метод сам открывает соединение и выполняет свою транзакцию.
