# CI/CD agent — начало

Пока только основной цикл в `agent.py`, по образцу `s01_agent_loop`
из learn-claude-code, с OpenAI-совместимым Chat Completions API.

Задача → модель → вызов `read_file` → результат обратно модели → ответ.
Цикл повторяется, пока модель вызывает инструмент (максимум 20 шагов).

Запуск в PowerShell:

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Заполни ключ, URL и модель в .env.
python agent.py
```

Пример задачи: `Прочитай README.md и объясни, что делает проект`.
После выполнения одной задачи программа завершается.
`.env` рядом с `agent.py` загружается автоматически. Переменные окружения имеют приоритет.

Для OpenRouter укажи `OPENAI_BASE_URL=https://openrouter.ai/api/v1`, ключ OpenRouter
в `OPENAI_API_KEY` и ID модели из OpenRouter в `OPENAI_MODEL`.
Для другого сервиса меняются те же три поля. URL — базовый адрес API, без `/chat/completions`.
Сервис и выбранная модель должны поддерживать Chat Completions с вызовом инструментов.

Инструмент читает файлы внутри текущей папки и передаёт содержимое выбранному API.
Дальше добавляем возможности по одной.
