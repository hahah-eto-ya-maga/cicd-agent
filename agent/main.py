import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from DB import Database
from worker import worker_loop


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    model = os.environ["MODEL_ID"]
    with OpenAI(
        base_url=os.getenv("OPENAI_BASE_URL"),
        api_key=os.getenv("OPENAI_API_KEY"),
    ) as client:
        db = Database()
        try:
            worker_loop(db, client, model)
        except KeyboardInterrupt:
            pass
        finally:
            db.close()


if __name__ == "__main__":
    main()
