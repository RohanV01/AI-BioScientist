FROM python:3.10-slim

WORKDIR /app

# System deps for scientific stack
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ cmake git curl \
    libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY scripts/ ./scripts/
COPY frontend/dist/ ./frontend/dist/

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
