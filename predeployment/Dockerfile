# The application image. Built on the internet-connected PC by predeployment\build.ps1 (build context: the
# repository root; .dockerignore lets in only backend/, frontend/ and db/). Runs on the offline VM with
# deployment/docker-compose.yml behind nginx. Nothing in it reaches the internet at run time.
FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_LISTEN=0.0.0.0:8080 \
    APP_THREADS=8 \
    FLASK_APP=wsgi

# Packages first (a code change does not reinstall them): runtime only, pinned by constraints.txt.
COPY backend/requirements.txt backend/constraints.txt /app/backend/
RUN pip install --no-cache-dir -r /app/backend/requirements.txt \
 && useradd --uid 10001 --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin app

COPY backend/ /app/backend/
COPY frontend/ /app/frontend/
COPY db/ /app/db/

# Byte-code compiled now (the container's filesystem is read-only); /app/data is the only writable folder
# (uploaded document files and scheduled reports; a host folder on the VM, see docker-compose.yml).
RUN python -m compileall -q /app/backend \
 && mkdir -p /app/data \
 && chown app:app /app/data

USER app
WORKDIR /app/backend
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=6s --start-period=40s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health', timeout=5).status == 200 else 1)"]
CMD ["python", "serve.py"]
