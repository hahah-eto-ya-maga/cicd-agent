def log_tool_call(name: str, args: dict) -> None:
    print(f"Тулза: {name} args: {args}")


def log_tool_result(name: str, args: dict | None, output: str) -> None:
    print(output[:200])
