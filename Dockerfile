# Dockerfile
# Basis: Playwright + Python, inkl. Chromium/Firefox/WebKit
FROM mcr.microsoft.com/playwright/python:v1.46.0-jammy

# Systemweite Settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Berlin

WORKDIR /app

# Optional: Nur requirements erst kopieren für besseren Layer-Cache
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# App-Code in das Image kopieren
# Erwartet später eine Struktur wie:
# /app/uploader/worker.py
# /app/uploader/targets/debeka.py
# /app/uploader/targets/ebeihilfe.py
COPY . /app

# Optional: Nicht-root User für mehr Sicherheit
# (Playwright-Image bringt bereits einen "pwuser" mit)
USER pwuser

# Standard-Kommando: den Worker starten
# Du kannst das via docker-compose überschreiben
CMD ["python", "-m", "uploader.worker"]