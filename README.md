# CI/CD Agent

Агент для поиска и исправления ошибок GitHub Actions. Получает задания из PostgreSQL,
подготавливает код нужного коммита и логи CI, затем работает с кодом через LLM и инструменты.

В Docker Compose запускаются агент, Flask-сервер для вебхуков, PostgreSQL и nginx.
Проект в разработке: запись заданий из вебхука и сохранение итогов пока не подключены.

## Запуск

Нужны Docker и Docker Compose.

```bash
cp .env.example .env
```

Заполни `.env`:

- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `MODEL_ID` — ключ, адрес API и модель с поддержкой вызова инструментов.
- `GITHUB_TOKEN` — токен аккаунта бота с доступом к репозиторию и логам Actions.
- `GITHUB_WEBHOOK_SECRET` — общий секрет с настройкой webhook в GitHub.
- `POSTGRES_PASSWORD` — пароль базы данных.

```bash
docker compose up --build -d
```

Проверка: [localhost:8080/health](http://localhost:8080/health).
Вебхук принимает `POST /webhook`; для GitHub нужен публичный HTTPS-адрес.

```bash
docker compose logs -f agent  # логи агента
docker compose down           # остановка
```

Данные и журналы сохраняются в Docker volumes. Подробнее — [DOCKER.md](DOCKER.md).
