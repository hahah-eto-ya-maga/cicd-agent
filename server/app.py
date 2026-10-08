import hashlib
import hmac
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, request
from werkzeug.middleware.proxy_fix import ProxyFix


load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

# Доверяем одному nginx. Порт приложения должен быть доступен только ему.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhook")
def webhook():
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not secret:
        return {"error": "GITHUB_WEBHOOK_SECRET is not configured"}, 503

    signature = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(
        secret.encode(), request.get_data(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature.encode(), expected.encode()):
        return {"error": "Invalid signature"}, 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return {"error": "Expected a JSON object"}, 400

    event = request.headers.get("X-GitHub-Event")
    if event == "ping":
        return {"status": "pong"}

    if event != "workflow_run" or payload.get("action") != "completed":
        return {"status": "ignored"}

    run = payload.get("workflow_run")
    if not isinstance(run, dict):
        return {"error": "Missing workflow_run"}, 400
    if run.get("conclusion") != "failure":
        return {"status": "ignored"}

    # Пока только фиксируем событие. Фоновый запуск агента подключим здесь позже.
    app.logger.warning("CI failure: run_id=%s", run.get("id"))
    return {"status": "received", "run_id": run.get("id")}
