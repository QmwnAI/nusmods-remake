# Backend Dockerfile — Python 3.12 slim, gunicorn.
#
# Build:   docker build -t nus-planner-backend backend/
# Run:     docker run -p 8080:8080 -e DATABASE_PATH=/data/planner.db -v $PWD/data:/data nus-planner-backend
#
# For Fly.io deployments this is the entrypoint referenced by fly.toml.
# Migrations run in the release_command (see fly.toml), NOT in the CMD, so
# a failed migration blocks the release rather than crashing the running
# instance with a half-migrated DB.

FROM python:3.12-slim AS base

# Non-root user for the app process. Fly.io mounts volumes owned by root by
# default; we `chown` the data dir in the entrypoint if needed.
RUN useradd --create-home --shell /bin/bash app

WORKDIR /app

# Install Python deps first (leverages Docker layer caching — deps change less often than code).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code.
COPY . .

# Data dir default — the volume mount in fly.toml overrides this at runtime.
ENV DATABASE_PATH=/data/planner.db
RUN mkdir -p /data && chown -R app:app /data /app

USER app

# The web port; matches fly.toml internal_port.
EXPOSE 8080

# gunicorn: 2 workers is fine for a small app + SQLite (which serializes writes anyway).
# Threads help handle NUSMods sync requests without blocking read traffic.
# Access logs to stdout — Fly.io collects those.
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "2", \
     "--threads", "4", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:app"]
