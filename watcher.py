import os
import sys
import signal
import time
import logging
import gc
import traceback
from pathlib import Path
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, Future

import torch

_original_torch_load = torch.load

@wraps(_original_torch_load)
def _patched_torch_load(*args, **kwargs):
    kwargs["weights_only"] = False

    return _original_torch_load(*args, **kwargs)

torch.load = _patched_torch_load

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
BEAM_SIZE = int(os.environ.get("BEAM_SIZE", "1"))
_raw_threads = int(os.environ.get("CPU_THREADS", "0"))
CPU_THREADS = _raw_threads if _raw_threads > 0 else max((os.cpu_count() or 4) // 2, 1)
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "1"))
HF_TOKEN = os.environ.get("HF_TOKEN", "")
DEVICE = "cpu"
COMPUTE_TYPE = "int8"
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".wma", ".aac"}

PROCESSING_SUFFIX = ".processing"
ERROR_SUFFIX = ".error"

shutting_down = False


def handle_shutdown(signum, _frame):
    global shutting_down
    sig_name = signal.Signals(signum).name
    log.info("Received %s — finishing current files and shutting down...", sig_name)
    shutting_down = True


signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)


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


def cleanup_stale_markers(watch_dir: Path):
    count = 0
    for f in watch_dir.iterdir():
        if not f.name.endswith(PROCESSING_SUFFIX):
            continue
        log.warning("Removing stale marker: %s", f.name)
        f.unlink(missing_ok=True)
        count += 1

    if count > 0:
        log.info("Cleaned up %d stale .processing marker(s)", count)


def load_models():
    log.info(
        "Loading WhisperX model: %s (device=%s, compute=%s, threads=%d, beam=%d)",
        WHISPER_MODEL, DEVICE, COMPUTE_TYPE, CPU_THREADS, BEAM_SIZE,
    )
    model = whisperx.load_model(
        WHISPER_MODEL,
        DEVICE,
        compute_type=COMPUTE_TYPE,
        cpu_threads=CPU_THREADS,
        num_workers=MAX_WORKERS,
    )

    diarize_model = None
    if HF_TOKEN:
        log.info("Loading diarization pipeline...")
        try:
            diarize_model = DiarizationPipeline(token=HF_TOKEN, device=DEVICE)
        except TypeError:
            diarize_model = DiarizationPipeline(use_auth_token=HF_TOKEN, device=DEVICE)
    else:
        log.warning("HF_TOKEN not set — diarization disabled. Set HF_TOKEN for speaker labels.")

    return model, diarize_model


def transcribe_file(audio_path: Path, model, diarize_model) -> str:
    log.info("Transcribing: %s", audio_path.name)
    start_time = time.monotonic()

    audio = whisperx.load_audio(str(audio_path))
    result = model.transcribe(audio, batch_size=BATCH_SIZE, language=LANGUAGE, beam_size=BEAM_SIZE)

    detected_lang = result.get("language", LANGUAGE or "unknown")
    log.info("[%s] Detected language: %s", audio_path.name, detected_lang)

    log.info("[%s] Aligning segments...", audio_path.name)
    model_a, metadata = whisperx.load_align_model(language_code=detected_lang, device=DEVICE)
    result = whisperx.align(result["segments"], model_a, metadata, audio, DEVICE, return_char_alignments=False)
    del model_a
    gc.collect()

    if diarize_model is not None:
        log.info("[%s] Diarizing speakers...", audio_path.name)
        diarize_segments = diarize_model(audio)
        result = whisperx.assign_word_speakers(diarize_segments, result)

    elapsed = time.monotonic() - start_time
    audio_duration = len(audio) / 16000
    rtf = audio_duration / elapsed if elapsed > 0 else 0
    log.info("[%s] Done in %.1fs (audio: %.1fs, speed: %.1fx RT)", audio_path.name, elapsed, audio_duration, rtf)

    return format_result(result["segments"])


def get_pending_files(watch_dir: Path) -> list[Path]:
    pending: list[Path] = []
    for f in watch_dir.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in AUDIO_EXTENSIONS:
            continue

        txt_path = f.with_suffix(".txt")
        error_path = f.with_suffix(f.suffix + ERROR_SUFFIX)
        processing_path = f.with_suffix(f.suffix + PROCESSING_SUFFIX)

        if txt_path.exists() or error_path.exists() or processing_path.exists():
            continue

        pending.append(f)

    return sorted(pending)


def process_file(audio_path: Path, model, diarize_model):
    processing_marker = audio_path.with_suffix(audio_path.suffix + PROCESSING_SUFFIX)
    txt_path = audio_path.with_suffix(".txt")
    error_path = audio_path.with_suffix(audio_path.suffix + ERROR_SUFFIX)

    try:
        processing_marker.touch()
        transcript = transcribe_file(audio_path, model, diarize_model)
        txt_path.write_text(transcript, encoding="utf-8")
        log.info("Result saved: %s", txt_path.name)
    except Exception:
        log.exception("Failed to process %s", audio_path.name)
        error_path.write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        processing_marker.unlink(missing_ok=True)


def main():
    log.info("WhisperRoles watcher starting")
    log.info("Watching: %s", WATCH_DIR)
    log.info(
        "Model: %s | Device: %s | Batch: %d | Beam: %d | Threads: %d | Workers: %d",
        WHISPER_MODEL, DEVICE, BATCH_SIZE, BEAM_SIZE, CPU_THREADS, MAX_WORKERS,
    )

    if not WATCH_DIR.exists():
        WATCH_DIR.mkdir(parents=True, exist_ok=True)
        log.info("Created watch directory: %s", WATCH_DIR)

    cleanup_stale_markers(WATCH_DIR)
    model, diarize_model = load_models()

    log.info("Watching for audio files... (poll every %ds)", POLL_INTERVAL)

    active_futures: dict[Path, Future] = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        while not shutting_down:
            active_futures = {p: f for p, f in active_futures.items() if not f.done()}

            pending = get_pending_files(WATCH_DIR)
            for audio_path in pending:
                if audio_path in active_futures:
                    continue
                future = executor.submit(process_file, audio_path, model, diarize_model)
                active_futures[audio_path] = future

            time.sleep(POLL_INTERVAL)

        log.info("Waiting for %d active task(s) to finish...", len(active_futures))
        for path, future in active_futures.items():
            future.result()
            log.info("Finished: %s", path.name)

    log.info("Shutdown complete.")


if __name__ == "__main__":
    main()
