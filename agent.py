"""Основной цикл: модель → инструмент → результат → модель."""

import json
import os
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv


SYSTEM = """Ты помощник для работы с кодом. Отвечай по-русски."""

TOOLS = [{
    "type": "function",
    "function": {
    "name": "read_file",
    "description": "Прочитать текстовый файл в текущей папке проекта.",
    "parameters": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
        "additionalProperties": False,
    },
    },
}]


def read_file(path: str) -> str:
    root = Path.cwd().resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Файл должен находиться внутри проекта")
    if any(part == ".git" or part.startswith(".env")
           for part in target.relative_to(root).parts):
        raise ValueError("Чтение .git и .env запрещено")
    with target.open(encoding="utf-8") as file:
        return file.read(30000)


def agent_loop(client: OpenAI, model: str, task: str) -> str:
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": task}]

    for _ in range(20):
        # 1. Отправляем задачу и предыдущие результаты инструментов модели.
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
        )
        choice = response.choices[0]
        if choice.finish_reason not in {"stop", "tool_calls"}:
            raise RuntimeError(f"Ответ модели не завершён: {choice.finish_reason}")
        message = choice.message
        messages.append(message.model_dump(exclude_none=True))

        # 2. Если инструментов нет — модель закончила работу.
        calls = message.tool_calls or []
        if not calls:
            return message.content or ""

        # 3. Выполняем инструменты и возвращаем результаты в следующий запрос.
        for call in calls:
            function = call.function
            print(f"Инструмент: {function.name}({function.arguments})")
            try:
                if function.name != "read_file":
                    raise ValueError(f"Неизвестный инструмент: {function.name}")
                args = json.loads(function.arguments)
                result = read_file(args["path"])
            except (OSError, ValueError, KeyError, TypeError) as error:
                result = f"Ошибка: {error}"
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            })

    raise RuntimeError("Достигнут лимит: 20 шагов агента")


if __name__ == "__main__":
    load_dotenv(Path(__file__).with_name(".env"))
    model = os.environ.get("OPENAI_MODEL")
    if not model or not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Задай OPENAI_API_KEY и OPENAI_MODEL в .env или окружении")
    client = OpenAI(base_url=os.environ.get("OPENAI_BASE_URL"))
    while True:
        try:
            task = input("Задача > ").strip()
            if task.lower() in {"exit", "quit"}:
                break
            if task:
                print(agent_loop(client, model, task))
        except (EOFError, KeyboardInterrupt):
            break
