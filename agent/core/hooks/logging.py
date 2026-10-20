import logging


def log_tool_call(logger: logging.Logger, name: str, args: dict) -> None:
    logger.info("Тулза: %s args: %s", name, args)


def log_tool_result(
    logger: logging.Logger, name: str, args: dict | None, output: str,
) -> None:
    logger.info("Результат %s:\n%s", name, output)
