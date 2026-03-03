FROM python:3.10-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    torch==2.6.0+cpu \
    torchaudio==2.6.0+cpu \
    --extra-index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir whisperx

COPY watcher.py /app/watcher.py

WORKDIR /app

ENV WATCH_DIR=/data
ENV WHISPER_MODEL=small
ENV BATCH_SIZE=8
ENV POLL_INTERVAL=5

VOLUME ["/data"]

CMD ["python", "-u", "watcher.py"]
