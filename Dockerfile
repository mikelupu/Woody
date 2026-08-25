FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HPT_STOCKFISH_PATH=/usr/games/stockfish \
    HPT_INSTANCE_PATH=/data

# Stockfish + build tools for wheels that ship no arm64 slim wheel yet.
RUN apt-get update \
 && apt-get install --no-install-recommends -y \
      stockfish \
      curl \
      ca-certificates \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency manifest first so Docker caches the install layer.
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Runtime deps only (no dev tools, no browser tests, no zstandard).
RUN pip install --no-cache-dir .

# Persistent progress DB will be mounted here at runtime.
RUN mkdir -p /data

EXPOSE 8000

# Railway (and most PaaS) injects $PORT; default to 8000 for local runs.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 1 --timeout 30 'hanging_piece_trainer.app:create_app()'"]
