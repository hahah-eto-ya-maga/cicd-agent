import io
import re
import zipfile
from urllib.parse import urlparse

import requests


class GitHubError(Exception):
    """Ошибка обращения к GitHub API или загрузки логов."""


class GitHubClient:
    def __init__(self, token: str | None = None, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "cicd-agent",
        })
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def _repository_path(self, repository: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise GitHubError("Ожидается репозиторий в формате owner/name")
        if any(part in {".", ".."} for part in repository.split("/")):
            raise GitHubError("Некорректное имя репозитория")
        return f"/repos/{repository}"

    def _request(self, method: str, path: str, status: int = 200, **kwargs):
        try:
            response = self.session.request(
                method, f"https://api.github.com{path}", timeout=self.timeout,
                allow_redirects=False, **kwargs,
            )
        except requests.RequestException as error:
            raise GitHubError("Не удалось обратиться к GitHub API") from error
        if response.status_code != status:
            code = response.status_code
            response.close()
            raise GitHubError(f"GitHub API: {method} {path} вернул HTTP {code}")
        return response

    def get_workflow_run(self, repository: str, run_id: int) -> dict:
        path = f"{self._repository_path(repository)}/actions/runs/{run_id}"
        with self._request("GET", path) as response:
            return response.json()

    def get_workflow_logs(self, repository: str, run_id: int, run_attempt: int) -> str:
        path = (
            f"{self._repository_path(repository)}/actions/runs/{run_id}"
            f"/attempts/{run_attempt}/logs"
        )
        # GitHub возвращает временную ссылку на ZIP, а не сами логи.
        with self._request("GET", path, status=302) as response:
            location = response.headers.get("Location", "")
        if urlparse(location).scheme != "https":
            raise GitHubError("GitHub не вернул HTTPS-ссылку на архив логов")

        limit = 50 * 1024 * 1024
        try:
            # Отдельный запрос: токен API не отправляется на хост архива.
            with requests.get(location, timeout=self.timeout, stream=True) as response:
                response.raise_for_status()
                archive = io.BytesIO()
                for chunk in response.iter_content(chunk_size=65536):
                    if archive.tell() + len(chunk) > limit:
                        raise GitHubError("Архив логов превышает 50 МиБ")
                    archive.write(chunk)

            archive.seek(0)
            with zipfile.ZipFile(archive) as logs:
                entries = [entry for entry in logs.infolist() if not entry.is_dir()]
                if sum(entry.file_size for entry in entries) > limit:
                    raise GitHubError("Распакованные логи превышают 50 МиБ")
                # Читаем в память, не извлекаем произвольные пути из ZIP на диск.
                return "\n\n".join(
                    f"=== {entry.filename} ===\n"
                    + logs.read(entry).decode("utf-8", errors="replace")
                    for entry in sorted(entries, key=lambda entry: entry.filename)
                )
        except (requests.RequestException, zipfile.BadZipFile, RuntimeError) as error:
            raise GitHubError("Не удалось скачать или прочитать архив логов CI") from error

    def create_pull_request(
        self, repository: str, title: str, head: str, base: str,
        body: str = "", draft: bool = True,
    ) -> dict:
        # Ветка head должна быть опубликована заранее. Сам метод не делает git push.
        path = f"{self._repository_path(repository)}/pulls"
        with self._request("POST", path, status=201, json={
            "title": title, "head": head, "base": base, "body": body, "draft": draft,
        }) as response:
            return response.json()

    def close(self):
        self.session.close()
