# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim

# System deps:
#   tesseract-ocr  — pytesseract
#   libgl1         — opencv-python
#   libglib2.0-0   — opencv-python
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

COPY --from=builder /install /usr/local
COPY . .

RUN mkdir -p /app/storage && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Use $PORT if Railway injects it, otherwise default to 8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
