FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (layer-cached)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY app.py /app/app.py

# Models are mounted as a read-only volume at runtime (see docker-compose.yml)
RUN mkdir -p /app/models

# Non-root user for security
RUN useradd --create-home --shell /usr/sbin/nologin mluser \
    && chown -R mluser:mluser /app

USER mluser

EXPOSE 8001

ENTRYPOINT ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
