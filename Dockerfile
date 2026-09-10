# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# system deps (gcc for any wheel that needs building; ca-certificates for TLS)
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# python deps first (better layer caching)
COPY requirements.txt .
RUN python -m pip install --upgrade pip \
 && python -m pip install -r requirements.txt

# app files
COPY shin.py .
COPY proxies.txt* ./

# Railway will set BOT_TOKEN and (optionally) DB_PATH
CMD ["python", "-u", "shin.py"]
