import os
import subprocess
import json

try:
    import readline
    readline.parse_and_bind('set bind-tty-special-chars off')
    readline.parse_and_bind('set input-meta on')
    readline.parse_and_bind('set output-meta on')
    readline.parse_and_bind('set convert-meta off')
except ImportError:
    pass

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(override=True)

client = OpenAI(
    base_url=os.getenv("OPENAI_BASE_URL"),
    api_key=os.getenv("OPENAI_API_KEY")
)

MODEL = os.environ.get("MODEL_ID", "deepseek/deepseek-v4-flash-free")
SYSTEM = f"You are a coding agent at {os.getcwd()}. Use bash to solve tasks. Act, don't explain."

TOOLS = [{
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Run a shell command.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string"}
            },
            "required": ["command"],
        },
    }
}]

def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(command, shell=True, cwd=os.getcwd(),
                       capture_output=True, text=True, errors="replace", timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except (FileNotFoundError, OSError) as e:
        return f"Error: {e}"

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
            return
            
        for tool_call in tool_calls:
            function_args = json.loads(tool_call.function.arguments)
            command = function_args.get("command")
            print(f"\033[33m$ {command}\033[0m")
            output = run_bash(command)
            print(output[:200])
            
            tool_result = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": output,
            }
            messages.append(tool_result)
            api_messages.append(tool_result)

if __name__ == "__main__":
    print("Enter a question, press Enter to send. Type q to quit.\n")
    history = []
    while True:
        try:
            query = input("\033[36ms01 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append({"role": "user", "content": query})
        agent_loop(history)
        
        last_msg = history[-1]
        if last_msg["role"] == "assistant" and last_msg.get("content"):
            print(last_msg["content"])
        print()
