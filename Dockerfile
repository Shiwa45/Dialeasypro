# ============================================================
# TeleCRM Backend — Dockerfile
# Multi-stage build: development + production
# ============================================================

# ---- Base Stage (shared) -----------------------------------
FROM python:3.12-slim AS base

# System dependencies for psycopg2, Pillow, lxml, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    libjpeg-dev \
    libpng-dev \
    zlib1g-dev \
    libxml2-dev \
    libxslt1-dev \
    curl \
    git \
    gettext \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on

# Create app user (non-root for security)
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

# Set working directory
WORKDIR /app

# ---- Development Stage ------------------------------------
FROM base AS development

# Install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Install dev extras
RUN pip install \
    django-debug-toolbar==4.4.6 \
    pytest==8.3.4 \
    pytest-django==4.9.0 \
    pytest-cov==6.0.0 \
    factory-boy==3.3.1 \
    black==24.10.0 \
    isort==5.13.2 \
    flake8==7.1.1 \
    flower==2.0.1 \
    ipython==8.30.0

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/staticfiles /app/mediafiles /var/log/telecrm && \
    chown -R appuser:appgroup /app /var/log/telecrm

# Don't switch to non-root in development for volume mount compatibility
USER appuser

EXPOSE 8000

# ---- Production Build Stage --------------------------------
FROM base AS production_builder

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ---- Production Stage --------------------------------------
FROM base AS production

# Copy installed packages from builder
COPY --from=production_builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=production_builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=appuser:appgroup . .

# Create necessary directories
RUN mkdir -p /app/staticfiles /app/mediafiles /var/log/telecrm && \
    chown -R appuser:appgroup /app /var/log/telecrm

# Collect static files during build
RUN DJANGO_SETTINGS_MODULE=config.settings.production \
    SECRET_KEY=dummy-build-key \
    DB_PASSWORD=dummy \
    python manage.py collectstatic --no-input 2>/dev/null || true

USER appuser

EXPOSE 8000

# Production entry: Daphne ASGI server
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "config.asgi:application", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120"]
