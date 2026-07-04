FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=3000

WORKDIR /app

# System libs for Pillow.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libjpeg62-turbo zlib1g \
    && rm -rf /var/lib/apt/lists/*

# Dependency layer, cached until pyproject changes. impersonate = the curl_cffi
# bypass backend (first in the default BYPASS_ORDER); FlareSolverr runs as the
# compose sidecar.
COPY pyproject.toml ./
RUN pip install --no-cache-dir '.[impersonate]'

# Replace the dependency layer's empty dist with the real package.
COPY app ./app
RUN pip install --no-cache-dir --no-deps .

# uid 1000 matches the default host user so the ./local and ./logs bind mounts stay writable.
RUN useradd --uid 1000 --user-group --home-dir /app --no-create-home phoenixadult \
    && mkdir -p /app/local /app/logs \
    && chown -R phoenixadult:phoenixadult /app/local /app/logs
USER phoenixadult

EXPOSE 3000
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '3000') + '/health')"
CMD ["python", "-m", "app.main"]
