# Stadio di build: compilatore e header libpq servono solo se una dipendenza va compilata
# (google-re2 ha un sdist come ripiego). L'immagine finale non li contiene.
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

FROM python:3.12-slim

WORKDIR /app

ENV PATH="/opt/venv/bin:$PATH"
COPY --from=builder /opt/venv /opt/venv

COPY backend/ .
COPY deploy/api/entrypoint.sh deploy/api/entrypoint.sh
# Template servito dal pulsante "Scarica lo script" nella pagina del receiver:
# una sola copia dello script, quella del repository (app/services/wrapper_script.py).
COPY scripts/notifyhub-run.sh scripts/notifyhub-run.sh

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app \
    && mkdir -p /var/lib/notifyhub/metrics && chown appuser:appuser /var/lib/notifyhub/metrics
USER appuser

EXPOSE 8000 9100
