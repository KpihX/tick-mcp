FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md /app/
COPY src /app/src
RUN python -m pip install --no-cache-dir .

COPY . /app/

RUN useradd -m tickmcp && chown -R tickmcp:tickmcp /app
USER tickmcp

EXPOSE 8091

CMD ["python", "-m", "tick_mcp.main", "serve-http"]
