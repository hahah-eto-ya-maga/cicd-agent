import os
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from services.database import Database
from services.github_client import GitHubClient
from services.repository_loader import RepositoryLoader
from services.task_logging import SecretFormatter
from worker import worker_loop


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(SecretFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[console])
    model = os.environ["MODEL_ID"]
    with OpenAI(
        base_url=os.getenv("OPENAI_BASE_URL"),
        api_key=os.getenv("OPENAI_API_KEY"),
    ) as client:
        db = Database()
        token = os.getenv("GITHUB_TOKEN")
        github = GitHubClient(token=token)
        loader = RepositoryLoader(repos_dir=Path("repos"), github=github)
        try:
            worker_loop(db, client, model, loader)
        except KeyboardInterrupt:
            pass
        finally:
            github.close()
            db.close()


if __name__ == "__main__":
    main()
