FROM python:3.11-slim

LABEL org.opencontainers.image.title="strain-kallfu-s3-pibench"
LABEL org.opencontainers.image.description="Strain Kallfu Zero - Pi-Bench Purple Agent for AgentBeats Sprint 3"
LABEL org.opencontainers.image.team="Strain Kallfu Zero"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY *.py ./

RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 9009

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:9009/health || exit 1

ENTRYPOINT ["python", "purple_server.py"]
CMD ["--host", "0.0.0.0", "--port", "9009"]
