import json
from pathlib import Path

from openai import OpenAI

from tools.definitions import TOOLS
from tools.files import run_edit, run_glob, run_read, run_write
from tools.shell import run_bash


class AgentSession:
    def __init__(self, client: OpenAI, model: str, workdir: Path):
        self.client = client
        self.model = model
        self.workdir = workdir.resolve()
        self.messages: list[dict] = []

    def submit(self, text: str) -> str:
        self.messages.append({"role": "user", "content": text})
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
            
            self.messages.append({
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": assistant_message.tool_calls
            })
            api_messages.append(assistant_message)
            
            tool_calls = assistant_message.tool_calls
            if not tool_calls:
                return assistant_message.content or ""
                
            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                print(f"Тулза: {tool_name}")
                try:
                    args = json.loads(tool_call.function.arguments)
                    print(f"Бро> {tool_name} args: {args}")
                    output = self._run_tool(tool_name, args)
                except json.JSONDecodeError:
                    output = "Error: Invalid JSON arguments from model"
                except TypeError as e:
                    output = f"Error: Invalid arguments for tool {tool_name}: {e}"
                except Exception as e:
                    output = f"Error: {e}"
                    
                print(str(output)[:200])
                
                tool_result = {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(output)
                }
                self.messages.append(tool_result)
                api_messages.append(tool_result)
