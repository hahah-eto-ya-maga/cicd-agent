import os
import re
import subprocess
from pathlib import Path

from services.github_client import GitHubClient, GitHubError
from models.Task import Task

class RepositoryLoadError(Exception):
    """Не удалось подготовить рабочую копию задания."""


class RepositoryLoader:
    def __init__(self, repos_dir: Path, github: GitHubClient, timeout: int = 120):
        self.repos_dir = repos_dir.resolve()
        self.github = github
        self.timeout = timeout

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

    def logs_path(self, repository: str, task_id: int) -> Path:
        workspace = self.workspace_path(repository, task_id)
        return workspace.parent.parent / "logs" / f"task-{task_id}"

    def prepare(self, task: Task) -> Path:
        """Вернуть рабочую папку только после подготовки кода и логов CI."""
        workspace = self.workspace_path(task["repository"], task["id"])
        self.load(task["repository"], task["commit_sha"], workspace)
        try:
            logs = self.github.get_workflow_logs(
                task["repository"], task["run_id"], task["run_attempt"],
            )
            # Не перезаписываем одноимённый файл из репозитория.
            with (workspace / "ci.log").open("x", encoding="utf-8") as file:
                file.write(logs)
        except (GitHubError, OSError) as error:
            raise RepositoryLoadError(f"Не удалось подготовить логи CI: {error}") from error
        return workspace

    def load(self, repository: str, commit_sha: str, workspace: Path) -> None:
        """Подготовить точный коммит; при ошибке выбросить RepositoryLoadError.

        Один экземпляр обслуживает последовательный worker. LFS и подмодули
        пока не загружаются. Скачивание и авторизация делегируются GitHubClient.
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
                self.github.fetch_commit(repository, commit_sha, cache)

            actual = self._git(
                "--git-dir", str(cache), "rev-parse", "--verify", f"{ref}^{{commit}}",
            ).stdout.strip()
            if actual != commit_sha:
                raise RepositoryLoadError("Коммит в кеше не совпадает с заданием")

            self._git(
                "--git-dir", str(cache), "worktree", "add", "--detach",
                str(workspace), commit_sha,
            )
        except (OSError, subprocess.TimeoutExpired, GitHubError) as error:
            raise RepositoryLoadError(f"Не удалось загрузить {repository}: {error}") from error

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, errors="replace",
            timeout=self.timeout, env=env,
        )
        if check and result.returncode != 0:
            raise RepositoryLoadError(result.stderr.strip() or "Команда Git завершилась ошибкой")
        return result
