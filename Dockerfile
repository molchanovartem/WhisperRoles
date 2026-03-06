FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    torch==2.8.0 torchaudio==2.8.0 --extra-index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir "pyannote-audio>=3.1,<4" \
    && pip install --no-cache-dir whisperx \
    && pip install --no-cache-dir fastapi uvicorn[standard] python-multipart

COPY app.py /app/app.py

WORKDIR /app

ENV RESULTS_DIR=/data/results
ENV WHISPER_MODEL=small
ENV BATCH_SIZE=8
ENV MAX_WORKERS=1

EXPOSE 8000

VOLUME ["/data"]

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
