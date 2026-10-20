def permission_hook(name: str, args: dict) -> str | None:
    # Здесь будут правила разрешений и запрос одобрения.
    # Пока хук ничего не запрещает. None — разрешить дальнейшую обработку.
    return None
