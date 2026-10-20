import os
import base64
import re
import subprocess
from pathlib import Path


class RepositoryLoadError(Exception):
    """Не удалось подготовить рабочую копию задания."""


class RepositoryLoader:
    def __init__(self, repos_dir: Path, timeout: int = 120, token: str | None = None):
        self.repos_dir = repos_dir.resolve()
        self.timeout = timeout
        self._token = token

    def _repository_dir(self, repository: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise RepositoryLoadError("Ожидается репозиторий в формате owner/name")
        if any(part in {".", ".."} for part in repository.split("/")):
            raise RepositoryLoadError("Некорректное имя репозитория")
        return self.repos_dir / repository.lower()

    def workspace_path(self, repository: str, task_id: int) -> Path:
        if not isinstance(task_id, int) or task_id <= 0:
            raise RepositoryLoadError("Ожидается положительный номер задания")
        return self._repository_dir(repository) / "workspaces" / f"task-{task_id}"

    def load(self, repository: str, commit_sha: str, workspace: Path) -> None:
        """Подготовить точный коммит; при ошибке выбросить RepositoryLoadError.

        Один экземпляр обслуживает последовательный worker. LFS и подмодули
        пока не загружаются. Токен для приватных репозиториев передаётся при создании.
        """
        repository_dir = self._repository_dir(repository)
        if not re.fullmatch(r"[0-9a-fA-F]{40}", commit_sha):
            raise RepositoryLoadError("Ожидается полный SHA коммита GitHub (40 символов)")

        commit_sha = commit_sha.lower()
        workspace = workspace.resolve()
        cache = repository_dir / "cache.git"
        if workspace == cache or cache in workspace.parents or workspace in cache.parents:
            raise RepositoryLoadError("Рабочая папка не должна пересекаться с Git-кешем")

        try:
            if workspace.exists() and (not workspace.is_dir() or any(workspace.iterdir())):
                raise RepositoryLoadError(f"Рабочая папка уже занята: {workspace}")
            workspace.parent.mkdir(parents=True, exist_ok=True)
            cache.parent.mkdir(parents=True, exist_ok=True)

            if not cache.exists():
                self._git("init", "--bare", "--template=", str(cache))

            # Постоянная ссылка сохраняет скачанный снимок в кеше между заданиями.
            ref = f"refs/commits/{commit_sha}"
            cached = self._git(
                "--git-dir", str(cache), "rev-parse", "--verify", ref,
                check=False,
            )
            if cached.returncode != 0:
                self._git(
                    "--git-dir", str(cache), "fetch", "--no-tags", "--depth=1",
                    f"https://github.com/{repository}.git", f"{commit_sha}:{ref}",
                )

            actual = self._git(
                "--git-dir", str(cache), "rev-parse", "--verify", f"{ref}^{{commit}}",
            ).stdout.strip()
            if actual != commit_sha:
                raise RepositoryLoadError("Коммит в кеше не совпадает с заданием")

            self._git(
                "--git-dir", str(cache), "worktree", "add", "--detach",
                str(workspace), commit_sha,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RepositoryLoadError(f"Не удалось загрузить {repository}: {error}") from error

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        credentials = None
        if self._token and "fetch" in args:
            credentials = base64.b64encode(f"x-access-token:{self._token}".encode()).decode()
            # Конфигурация только для subprocess: секрет не попадает в URL,
            # аргументы команды или файлы Git-кеша.
            index = int(env.get("GIT_CONFIG_COUNT", "0"))
            env["GIT_CONFIG_COUNT"] = str(index + 1)
            env[f"GIT_CONFIG_KEY_{index}"] = "http.https://github.com/.extraheader"
            env[f"GIT_CONFIG_VALUE_{index}"] = f"Authorization: Basic {credentials}"
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, errors="replace",
            timeout=self.timeout, env=env,
        )
        if check and result.returncode != 0:
            message = result.stderr.strip() or "Команда Git завершилась ошибкой"
            if self._token:
                message = message.replace(self._token, "***")
            if credentials:
                message = message.replace(credentials, "***")
            raise RepositoryLoadError(message)
        return result
