# WhisperRoles

Docker container that watches a directory for audio files and transcribes them with speaker diarization using [WhisperX](https://github.com/m-bain/whisperX). CPU-only.

## Quick Start

```bash
docker run -d \
  -v /path/to/audio:/data \
  -e HF_TOKEN=hf_your_token \
  ghcr.io/YOUR_GITHUB_USER/whisperroles:latest
```

Drop an `.mp3` (or `.wav`, `.m4a`, `.flac`, `.ogg`) into the mounted directory — a `.txt` file with the transcript will appear next to it.

## HuggingFace Token (required for diarization)

Speaker diarization uses pyannote.audio which requires a HuggingFace token:

1. Create account at [huggingface.co](https://huggingface.co)
2. Accept the license for [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1)
3. Create a read token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
4. Pass it as `HF_TOKEN` env var

Without `HF_TOKEN` the container still works but won't label speakers.

## Output Format

```
[00:00:01 - 00:00:05] SPEAKER_00: Hello, how are you?
[00:00:06 - 00:00:10] SPEAKER_01: I'm fine, thanks.
[00:00:11 - 00:00:18] SPEAKER_00: Great, let's get started.
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `WATCH_DIR` | `/data` | Directory to watch for audio files |
| `HF_TOKEN` | — | HuggingFace token for speaker diarization |
| `WHISPER_MODEL` | `small` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large-v2`, `large-v3-turbo`) |
| `LANGUAGE` | auto-detect | Force language code (e.g. `ru`, `en`) |
| `BATCH_SIZE` | `8` | Batch size for transcription |
| `POLL_INTERVAL` | `5` | Seconds between directory scans |

## Build Locally

```bash
docker build -t whisper-roles .
docker run -d -v $(pwd)/audio:/data -e HF_TOKEN=hf_xxx whisper-roles
```
