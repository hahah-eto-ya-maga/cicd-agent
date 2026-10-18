FROM python:3.12-slim AS builder
WORKDIR /build
COPY agent/requirements.txt .
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim AS runtime
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN useradd --create-home --uid 10001 app && mkdir /app/workspaces && chown app:app /app/workspaces
COPY --from=builder /opt/venv /opt/venv
COPY agent/ /app/agent/
USER app
CMD ["python", "agent/main.py"]
