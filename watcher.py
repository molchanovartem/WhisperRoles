import os
import sys
import time
import logging
import gc
from pathlib import Path

import whisperx
from whisperx.diarize import DiarizationPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("whisper-roles")

WATCH_DIR = Path(os.environ.get("WATCH_DIR", "/data"))
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "5"))
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
LANGUAGE = os.environ.get("LANGUAGE", None)
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "8"))
HF_TOKEN = os.environ.get("HF_TOKEN", "")
DEVICE = "cpu"
COMPUTE_TYPE = "int8"
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".wma", ".aac"}

PROCESSING_SUFFIX = ".processing"


def format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)

    return f"{h:02d}:{m:02d}:{s:02d}"


def format_result(segments: list[dict]) -> str:
    lines: list[str] = []
    for seg in segments:
        speaker = seg.get("speaker", "UNKNOWN")
        start = format_timestamp(seg.get("start", 0))
        end = format_timestamp(seg.get("end", 0))
        text = seg.get("text", "").strip()
        lines.append(f"[{start} - {end}] {speaker}: {text}")

    return "\n".join(lines)


def load_models():
    log.info("Loading WhisperX model: %s (device=%s, compute=%s)", WHISPER_MODEL, DEVICE, COMPUTE_TYPE)
    model = whisperx.load_model(WHISPER_MODEL, DEVICE, compute_type=COMPUTE_TYPE)

    diarize_model = None
    if HF_TOKEN:
        log.info("Loading diarization pipeline...")
        diarize_model = DiarizationPipeline(token=HF_TOKEN, device=DEVICE)
    else:
        log.warning("HF_TOKEN not set — diarization disabled. Set HF_TOKEN for speaker labels.")

    return model, diarize_model


def transcribe_file(audio_path: Path, model, diarize_model) -> str:
    log.info("Transcribing: %s", audio_path.name)

    audio = whisperx.load_audio(str(audio_path))
    result = model.transcribe(audio, batch_size=BATCH_SIZE, language=LANGUAGE)

    detected_lang = result.get("language", LANGUAGE or "unknown")
    log.info("Detected language: %s", detected_lang)

    log.info("Aligning segments...")
    model_a, metadata = whisperx.load_align_model(language_code=detected_lang, device=DEVICE)
    result = whisperx.align(result["segments"], model_a, metadata, audio, DEVICE, return_char_alignments=False)
    del model_a
    gc.collect()

    if diarize_model is not None:
        log.info("Diarizing speakers...")
        diarize_segments = diarize_model(audio)
        result = whisperx.assign_word_speakers(diarize_segments, result)

    return format_result(result["segments"])


def get_pending_files(watch_dir: Path) -> list[Path]:
    pending: list[Path] = []
    for f in watch_dir.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in AUDIO_EXTENSIONS:
            continue

        txt_path = f.with_suffix(".txt")
        processing_path = f.with_suffix(f.suffix + PROCESSING_SUFFIX)

        if txt_path.exists() or processing_path.exists():
            continue

        pending.append(f)

    return sorted(pending)


def process_file(audio_path: Path, model, diarize_model):
    processing_marker = audio_path.with_suffix(audio_path.suffix + PROCESSING_SUFFIX)
    txt_path = audio_path.with_suffix(".txt")

    try:
        processing_marker.touch()
        transcript = transcribe_file(audio_path, model, diarize_model)
        txt_path.write_text(transcript, encoding="utf-8")
        log.info("Result saved: %s", txt_path.name)
    except Exception:
        log.exception("Failed to process %s", audio_path.name)
    finally:
        processing_marker.unlink(missing_ok=True)


def main():
    log.info("WhisperRoles watcher starting")
    log.info("Watching: %s", WATCH_DIR)
    log.info("Model: %s | Device: %s | Batch: %d", WHISPER_MODEL, DEVICE, BATCH_SIZE)

    if not WATCH_DIR.exists():
        WATCH_DIR.mkdir(parents=True, exist_ok=True)
        log.info("Created watch directory: %s", WATCH_DIR)

    model, diarize_model = load_models()

    log.info("Watching for audio files... (poll every %ds)", POLL_INTERVAL)
    while True:
        pending = get_pending_files(WATCH_DIR)
        for audio_path in pending:
            process_file(audio_path, model, diarize_model)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
