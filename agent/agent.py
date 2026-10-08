import os
import subprocess
import json
import time
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(override=True)

WORKDIR = Path.cwd()

client = OpenAI(
    base_url=os.getenv("OPENAI_BASE_URL"),
    api_key=os.getenv("OPENAI_API_KEY")
)

MODEL = os.environ.get("MODEL_ID")
SYSTEM = f"You are a coding agent at {WORKDIR}"

def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR,
                           capture_output=True, text=True, errors="replace",
                           timeout=120)
        out = f"Код завершения: {r.returncode}\n{r.stdout}{r.stderr}".strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except (FileNotFoundError, OSError) as e:
        return f"Error: {e}"

def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path

def run_read(path: str, limit: int | None = None) -> str:
    try:
        lines = safe_path(path).read_text(encoding="utf-8").splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"

def run_write(path: str, content: str) -> str:
    try:
        file_path = safe_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"

def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        file_path = safe_path(path)
        text = file_path.read_text(encoding="utf-8")
        if old_text not in text:
            return f"Error: text not found in {path}"
        file_path.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"

def run_glob(pattern: str) -> str:
    import glob as g
    try:
        matches = sorted({
            match for match in g.glob(pattern, root_dir=WORKDIR, recursive=True)
            if (WORKDIR / match).resolve().is_relative_to(WORKDIR)
        })
        shown = matches[:200]
        if len(matches) > 200:
            shown.append("... (more matches omitted; narrow the pattern)")
        return "\n".join(shown) if shown else "(no matches)"
    except Exception as e:
        return f"Error: {e}"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "limit": {"type": "integer"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace exact text in a file once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"}
                },
                "required": ["path", "old_text", "new_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Find files matching a glob pattern; ** matches recursively.",
            "parameters": {
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"]
            }
        }
    }
]

TOOL_HANDLERS = {
    "bash": run_bash,
    "read_file": run_read,
    "write_file": run_write,
    "edit_file": run_edit,
    "glob": run_glob,
}

def agent_loop(messages: list):
    api_messages = [{"role": "system", "content": SYSTEM}] + messages
    while True:
        response = client.chat.completions.create(
            model=MODEL,
            messages=api_messages,
            tools=TOOLS,
            max_tokens=8000,
        )
        assistant_message = response.choices[0].message
        
        messages.append({
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
            handler = TOOL_HANDLERS.get(tool_name)
            try:
                args = json.loads(tool_call.function.arguments)
                print(f"Бро> {tool_name} args: {args}")
                output = handler(**args) if handler else f"Unknown tool: {tool_name}"
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
            messages.append(tool_result)
            api_messages.append(tool_result)

def worker_loop():
    global WORKDIR, SYSTEM

    workspaces = Path("workspaces").resolve()
    # Здесь подключиться к PostgreSQL.

    while True:
        task = None
        # Здесь получить task из PostgreSQL: забрать queued и пометить running
        # одной транзакцией. task — словарь с id, repository, commit_sha,
        # run_id и run_attempt. Пока подключения нет, task остаётся None.

        if task is None:
            time.sleep(2)
            continue

        try:
            workspace = workspaces / f"task-{task['id']}"
            workspace.mkdir(parents=True, exist_ok=True)

            # Здесь скачать repository в workspace на точном commit_sha.
            # Здесь скачать логи run_id / run_attempt и сохранить в ci.log.

            WORKDIR = workspace
            SYSTEM = f"You are a coding agent at {WORKDIR}. Use tools to solve tasks."
            messages = [{
                "role": "user",
                "content": (
                    f"Исправь падение CI в {task['repository']}. "
                    f"Код находится в {workspace}. Логи находятся в ci.log. "
                    "Найди причину, исправь код и запусти проверки."
                ),
            }]
            result = agent_loop(messages)

            # Здесь сохранить result и результаты проверок в PostgreSQL.
            # По результатам проверок определить итоговый статус задания.
        except Exception as error:
            print(f"Ошибка задания {task['id']}: {error}")
            # Здесь записать ошибку и статус failed в PostgreSQL.


if __name__ == "__main__":
    try:
        worker_loop()
    except KeyboardInterrupt:
        pass
