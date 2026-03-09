# Production image for the async Python ingress proxy.
# Use slim base to minimize package footprint and attack surface.
FROM python:3.11-slim

# Keep Python runtime predictable and avoid unnecessary bytecode/cache files.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Application code lives under /app.
WORKDIR /app

# Install only required Python runtime dependencies.
# --no-cache-dir reduces layer size by avoiding pip cache retention.
RUN pip install --no-cache-dir \
    aiohttp \
    python-dotenv \
    uvloop \
    numpy

# Copy proxy application source after dependency installation for better layer reuse.
COPY . /app

# Create a dedicated non-root runtime account.
# Security: shell is set to /usr/sbin/nologin to disable interactive shell access.
RUN useradd --create-home --home-dir /home/appuser --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Run as non-root to limit impact of a compromise.
USER appuser

# Expose ingress service ports.
EXPOSE 8080 8443

# Start the async ingress proxy server.
ENTRYPOINT ["python", "proxy_server.py"]
