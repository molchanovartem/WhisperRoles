import os
import sys
import uuid
import logging
import threading
from pathlib import Path
from multiprocessing import Process

from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.responses import PlainTextResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("whisper-roles")

RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", "/data/results"))
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="WhisperRoles API")

jobs: dict[str, str] = {}
_lock = threading.Lock()


def _worker(job_id: str, audio_path_str: str, results_dir_str: str):
    """Runs in a child process — all memory freed on exit."""
    import gc
    import time
    import traceback
    from functools import wraps
    from pathlib import Path

    import torch

    _original_torch_load = torch.load

    @wraps(_original_torch_load)
    def _patched_torch_load(*args, **kwargs):
        kwargs["weights_only"] = False

        return _original_torch_load(*args, **kwargs)

    torch.load = _patched_torch_load

    import whisperx
    from whisperx.diarize import DiarizationPipeline

    audio_path = Path(audio_path_str)
    results_dir = Path(results_dir_str)
    whisper_model_name = os.environ.get("WHISPER_MODEL", "small")
    language = os.environ.get("LANGUAGE", None) or None
    batch_size = int(os.environ.get("BATCH_SIZE", "8"))
    hf_token = os.environ.get("HF_TOKEN", "")
    device = "cpu"
    compute_type = "int8"

    def format_timestamp(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)

        return f"{h:02d}:{m:02d}:{s:02d}"

    try:
        print(f"[{job_id}] Loading models...", flush=True)
        model = whisperx.load_model(whisper_model_name, device, compute_type=compute_type)

        diarize_model = None
        if hf_token:
            print(f"[{job_id}] Loading diarization pipeline...", flush=True)
            try:
                diarize_model = DiarizationPipeline(token=hf_token, device=device)
            except TypeError:
                diarize_model = DiarizationPipeline(use_auth_token=hf_token, device=device)
        else:
            print(f"[{job_id}] HF_TOKEN not set — diarization disabled", flush=True)

        start_time = time.monotonic()

        audio = whisperx.load_audio(str(audio_path))
        result = model.transcribe(audio, batch_size=batch_size, language=language)

        detected_lang = result.get("language", language or "unknown")
        print(f"[{job_id}] Detected language: {detected_lang}", flush=True)

        print(f"[{job_id}] Aligning segments...", flush=True)
        model_a, metadata = whisperx.load_align_model(language_code=detected_lang, device=device)
        result = whisperx.align(
            result["segments"], model_a, metadata, audio, device,
            return_char_alignments=False,
        )
        del model_a
        gc.collect()

        if diarize_model is not None:
            print(f"[{job_id}] Diarizing speakers...", flush=True)
            diarize_segments = diarize_model(audio)
            result = whisperx.assign_word_speakers(diarize_segments, result)

        elapsed = time.monotonic() - start_time
        audio_duration = len(audio) / 16000
        rtf = audio_duration / elapsed if elapsed > 0 else 0
        print(
            f"[{job_id}] Done in {elapsed:.1f}s (audio: {audio_duration:.1f}s, speed: {rtf:.1f}x RT)",
            flush=True,
        )

        lines = []
        for seg in result["segments"]:
            speaker = seg.get("speaker", "UNKNOWN")
            start = format_timestamp(seg.get("start", 0))
            end = format_timestamp(seg.get("end", 0))
            text = seg.get("text", "").strip()
            lines.append(f"[{start} - {end}] {speaker}: {text}")

        result_path = results_dir / f"{job_id}.txt"
        result_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"[{job_id}] Job complete", flush=True)

    except Exception:
        print(f"[{job_id}] Job failed:", flush=True)
        traceback.print_exc()
        error_path = results_dir / f"{job_id}.error"
        error_path.write_text(traceback.format_exc(), encoding="utf-8")

    finally:
        audio_path.unlink(missing_ok=True)


def _run_job(job_id: str, audio_path: Path):
    with _lock:
        proc = Process(target=_worker, args=(job_id, str(audio_path), str(RESULTS_DIR)))
        proc.start()
        proc.join()

    result_file = RESULTS_DIR / f"{job_id}.txt"
    error_file = RESULTS_DIR / f"{job_id}.error"

    if result_file.exists():
        jobs[job_id] = "done"
    elif error_file.exists():
        jobs[job_id] = "error"
    else:
        jobs[job_id] = "error"
        error_file.write_text("Worker process exited without result", encoding="utf-8")

    log.info("[%s] Worker process finished, status: %s", job_id, jobs[job_id])


@app.post("/transcribe")
async def upload_audio(file: UploadFile):
    if not file.filename:
        raise HTTPException(400, "No file provided")

    job_id = str(uuid.uuid4())
    tmp_path = Path(f"/tmp/{job_id}_{file.filename}")

    content = await file.read()
    tmp_path.write_bytes(content)

    jobs[job_id] = "processing"

    thread = threading.Thread(target=_run_job, args=(job_id, tmp_path), daemon=True)
    thread.start()

    return {"job_id": job_id, "status": "processing"}


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    status = jobs.get(job_id)
    if not status:
        raise HTTPException(404, "Job not found")

    return {"job_id": job_id, "status": status}


@app.get("/result/{job_id}")
async def get_result(job_id: str):
    status = jobs.get(job_id)
    if not status:
        raise HTTPException(404, "Job not found")

    if status == "processing":
        raise HTTPException(202, "Still processing")

    if status == "error":
        error_path = RESULTS_DIR / f"{job_id}.error"
        error_text = error_path.read_text(encoding="utf-8") if error_path.exists() else "Unknown error"
        raise HTTPException(500, error_text)

    result_path = RESULTS_DIR / f"{job_id}.txt"
    if not result_path.exists():
        raise HTTPException(500, "Result file missing")

    return PlainTextResponse(result_path.read_text(encoding="utf-8"))


@app.get("/health")
async def health():
    return {"status": "ok"}
