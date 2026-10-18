BEGIN;

CREATE TABLE IF NOT EXISTS tasks (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository TEXT NOT NULL,
    run_id BIGINT NOT NULL CHECK (run_id > 0),
    run_attempt INTEGER NOT NULL DEFAULT 1 CHECK (run_attempt > 0),
    commit_sha TEXT NOT NULL,
    branch TEXT,

    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    result TEXT,
    error TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,

    CONSTRAINT tasks_run_unique UNIQUE (repository, run_id, run_attempt)
);

-- Очередь: сначала самое старое ожидающее задание, при равенстве времени — по id.
CREATE INDEX IF NOT EXISTS tasks_queued_order_idx
    ON tasks (created_at, id) WHERE status = 'queued';

COMMIT;
