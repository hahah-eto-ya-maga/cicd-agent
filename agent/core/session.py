import json
import logging
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any, Literal

from openai import OpenAI

from core.hooks.logging import log_tool_call, log_tool_result
from core.hooks.permissions import permission_hook
from core.tools.definitions import TOOLS
from core.tools.files import run_edit, run_glob, run_read, run_write
from core.tools.shell import run_bash


HookEvent = Literal["UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"]


class AgentSession:
    def __init__(
        self, client: OpenAI, model: str, workdir: Path,
        logger: logging.Logger | None = None,
    ):
        self.client = client
        self.model = model
        self.workdir = workdir.resolve()
        self.messages: list[dict] = []
        self.logger = logger if logger is not None else logging.getLogger(__name__)
        self.hooks: dict[HookEvent, list[Callable[..., str | None]]] = {
            "UserPromptSubmit": [],
            "PreToolUse": [],
            "PostToolUse": [],
            "Stop": [],
        }
        self.register_hook("PreToolUse", permission_hook)
        self.register_hook("PreToolUse", partial(log_tool_call, self.logger))
        self.register_hook("PostToolUse", partial(log_tool_result, self.logger))

    def register_hook(self, event: HookEvent, callback: Callable[..., str | None]):
        self.hooks[event].append(callback)

    def trigger_hooks(self, event: HookEvent, *args: Any) -> str | None:
        # None — продолжать; строка — остановить цепочку и вернуть причину.
        for callback in self.hooks[event]:
            result = callback(*args)
            if result is not None:
                return result
        return None

    def submit(self, text: str) -> str:
        self.logger.info("Задача:\n%s", text)
        self.messages.append({"role": "user", "content": text})
        # callback(text); результат этого события не меняет управление.
        self.trigger_hooks("UserPromptSubmit", text)
        return self._run_query()

    def _run_tool(self, name: str, arguments: dict) -> str:
        if name == "bash":
            return run_bash(self.workdir, **arguments)
        if name == "read_file":
            return run_read(self.workdir, **arguments)
        if name == "write_file":
            return run_write(self.workdir, **arguments)
        if name == "edit_file":
            return run_edit(self.workdir, **arguments)
        if name == "glob":
            return run_glob(self.workdir, **arguments)
        return f"Unknown tool: {name}"

    def _run_query(self) -> str:
        api_messages = [{
            "role": "system",
            "content": (
                f"You are a coding agent at {self.workdir}. Use tools to solve tasks."
            ),
        }] + self.messages
        while True:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=api_messages,
                tools=TOOLS,
                max_tokens=8000,
            )
            assistant_message = response.choices[0].message
            if assistant_message.content:
                self.logger.info("Агент:\n%s", assistant_message.content)
            
            self.messages.append({
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": assistant_message.tool_calls
            })
            api_messages.append(assistant_message)
            
            tool_calls = assistant_message.tool_calls
            if not tool_calls:
                # callback(messages); строка возвращает задачу модели на доработку.
                reason = self.trigger_hooks("Stop", self.messages)
                if reason is not None:
                    self.logger.info("Stop вернул задачу на доработку: %s", reason)
                    message = {"role": "user", "content": reason}
                    self.messages.append(message)
                    api_messages.append(message)
                    continue
                return assistant_message.content or ""
                
            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                args = None
                try:
                    args = json.loads(tool_call.function.arguments)
                    # callback(name, args); строка запрещает выполнение инструмента.
                    blocked = self.trigger_hooks("PreToolUse", tool_name, args)
                    if blocked is not None:
                        output = blocked
                    else:
                        output = self._run_tool(tool_name, args)
                except json.JSONDecodeError:
                    output = "Error: Invalid JSON arguments from model"
                except TypeError as e:
                    output = f"Error: Invalid arguments for tool {tool_name}: {e}"
                except Exception as e:
                    output = f"Error: {e}"

                # callback(name, args, output); args=None при ошибке JSON.
                # Событие наблюдает результат, включая отказы и ошибки.
                self.trigger_hooks(
                    "PostToolUse", tool_name, args, str(output)
                )
                
                tool_result = {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(output)
                }
                self.messages.append(tool_result)
                api_messages.append(tool_result)
