import subprocess
from pathlib import Path


def run_bash(workdir: Path, command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(command, shell=True, cwd=workdir,
                           capture_output=True, text=True, errors="replace",
                           timeout=120)
        out = f"Код завершения: {r.returncode}\n{r.stdout}{r.stderr}".strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except (FileNotFoundError, OSError) as e:
        return f"Error: {e}"

