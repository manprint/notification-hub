FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ .
COPY deploy/api/entrypoint.sh deploy/api/entrypoint.sh
# Template servito dal pulsante "Scarica lo script" nella pagina del receiver:
# una sola copia dello script, quella del repository (app/services/wrapper_script.py).
COPY scripts/notifyhub-run.sh scripts/notifyhub-run.sh

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000 9100
