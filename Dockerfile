FROM python:3.11-slim

LABEL org.opencontainers.image.title="WhatsApp Automation Tool" \
      org.opencontainers.image.description="Send personalized WhatsApp messages to business leads from a Docker web dashboard" \
      org.opencontainers.image.source="https://github.com/firaslamouchi21/-WhatsApp-Automation-Tool" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUTF8=1
ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:99

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    xvfb \
    x11-utils \
    x11-xserver-utils \
    xauth \
    xdg-utils \
    xdotool \
    scrot \
    fluxbox \
    x11vnc \
    novnc \
    websockify \
    chromium \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-send.txt ./
COPY web_ui/requirements.txt ./web_ui/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r web_ui/requirements.txt -r requirements-send.txt && \
    pip install --no-cache-dir pytest pytest-mock

COPY web_ui/ ./web_ui/
COPY src/ ./src/
COPY config/ ./config/
COPY templates/ ./templates/
COPY tests/ ./tests/
COPY main.py pyproject.toml ./

RUN mkdir -p logs data output

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

EXPOSE 5000 6080 5900

# "serve" starts the GUI stack + web UI; any other command runs straight through
# (e.g. `docker run <img> python main.py --list-templates`).
CMD ["serve"]
