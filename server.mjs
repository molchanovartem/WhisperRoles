import { createReadStream, existsSync, mkdirSync, writeFileSync, readFileSync, unlinkSync, renameSync, statSync } from "node:fs";
import { join, basename, extname } from "node:path";
import { execSync } from "node:child_process";
import { tmpdir } from "node:os";
import express from "express";
import multer from "multer";
import { v4 as uuidv4 } from "uuid";
import OpenAI from "openai";

const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
if (!OPENAI_API_KEY) {
  console.error("OPENAI_API_KEY environment variable is required");
  process.exit(1);
}

const PORT = parseInt(process.env.PORT || "8000", 10);
const RESULTS_DIR = process.env.RESULTS_DIR || "/data/results";
const MAX_CHUNK_MB = 24;

mkdirSync(RESULTS_DIR, { recursive: true });

const openai = new OpenAI({ apiKey: OPENAI_API_KEY });
const app = express();
const upload = multer({ dest: tmpdir() });

const jobs = new Map();

function formatTimestamp(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);

  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function splitAudio(inputPath) {
  const fileSizeMb = statSync(inputPath).size / (1024 * 1024);
  if (fileSizeMb <= MAX_CHUNK_MB) {
    return [inputPath];
  }

  const durationOut = execSync(
    `ffprobe -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "${inputPath}"`,
    { encoding: "utf-8" },
  );
  const totalDuration = parseFloat(durationOut.trim());
  const numChunks = Math.ceil(fileSizeMb / MAX_CHUNK_MB);
  const chunkDuration = totalDuration / numChunks;

  const tmpDir = join(tmpdir(), `whisper-${uuidv4()}`);
  mkdirSync(tmpDir, { recursive: true });

  const chunks = [];
  for (let i = 0; i < numChunks; i++) {
    const start = i * chunkDuration;
    const chunkPath = join(tmpDir, `chunk_${String(i).padStart(3, "0")}.mp3`);
    execSync(
      `ffmpeg -y -i "${inputPath}" -ss ${start} -t ${chunkDuration} -acodec libmp3lame -q:a 4 "${chunkPath}"`,
      { stdio: "ignore" },
    );
    if (existsSync(chunkPath)) {
      chunks.push(chunkPath);
    }
  }

  return chunks;
}

async function transcribeChunk(filePath) {
  const response = await openai.audio.transcriptions.create({
    model: "gpt-4o-transcribe-diarize",
    file: createReadStream(filePath),
    response_format: "diarized_json",
    chunking_strategy: "auto",
  });

  return response.segments.map((seg) => ({
    speaker: seg.speaker,
    text: seg.text,
    start: seg.start,
    end: seg.end,
  }));
}

function formatSegments(segments) {
  return segments
    .map((seg) => {
      const start = formatTimestamp(seg.start ?? 0);
      const end = formatTimestamp(seg.end ?? 0);
      const speaker = seg.speaker ?? "UNKNOWN";

      return `[${start} - ${end}] ${speaker}: ${seg.text?.trim() ?? ""}`;
    })
    .join("\n");
}

async function processJob(jobId, audioPath) {
  let chunks = [];
  try {
    console.log(`[${jobId}] Starting transcription: ${basename(audioPath)}`);
    chunks = splitAudio(audioPath);

    const allSegments = [];
    let timeOffset = 0;

    for (let i = 0; i < chunks.length; i++) {
      console.log(`[${jobId}] Processing chunk ${i + 1}/${chunks.length}`);
      const segments = await transcribeChunk(chunks[i]);

      for (const seg of segments) {
        seg.start += timeOffset;
        seg.end += timeOffset;
      }

      if (segments.length > 0) {
        timeOffset = segments[segments.length - 1].end;
      }

      allSegments.push(...segments);
    }

    const resultText = formatSegments(allSegments);
    writeFileSync(join(RESULTS_DIR, `${jobId}.txt`), resultText, "utf-8");

    jobs.set(jobId, "done");
    console.log(`[${jobId}] Transcription complete: ${allSegments.length} segments`);
  } catch (err) {
    console.error(`[${jobId}] Transcription failed:`, err.message);
    writeFileSync(join(RESULTS_DIR, `${jobId}.error`), String(err.stack ?? err), "utf-8");
    jobs.set(jobId, "error");
  } finally {
    tryUnlink(audioPath);
    for (const chunk of chunks) {
      if (chunk !== audioPath) {
        tryUnlink(chunk);
      }
    }
  }
}

function tryUnlink(filePath) {
  try {
    unlinkSync(filePath);
  } catch {}
}

function toMp3(inputPath) {
  const mp3Path = inputPath.replace(/\.[^.]+$/, "") + ".mp3";
  if (inputPath.endsWith(".mp3")) {
    return inputPath;
  }

  execSync(
    `ffmpeg -y -i "${inputPath}" -acodec libmp3lame -q:a 4 "${mp3Path}"`,
    { stdio: "ignore" },
  );
  tryUnlink(inputPath);

  return mp3Path;
}

app.post("/transcribe", upload.single("file"), (req, res) => {
  if (!req.file) {
    return res.status(400).json({ error: "No file provided" });
  }

  const ext = extname(req.file.originalname).toLowerCase() || ".bin";
  const namedPath = req.file.path + ext;
  renameSync(req.file.path, namedPath);

  const mp3Path = toMp3(namedPath);

  const jobId = uuidv4();
  jobs.set(jobId, "processing");

  processJob(jobId, mp3Path);

  res.json({ job_id: jobId, status: "processing" });
});

app.get("/status/:jobId", (req, res) => {
  const status = jobs.get(req.params.jobId);
  if (!status) {
    return res.status(404).json({ error: "Job not found" });
  }

  res.json({ job_id: req.params.jobId, status });
});

app.get("/result/:jobId", (req, res) => {
  const { jobId } = req.params;
  const status = jobs.get(jobId);

  if (!status) {
    return res.status(404).json({ error: "Job not found" });
  }

  if (status === "processing") {
    return res.status(202).json({ error: "Still processing" });
  }

  if (status === "error") {
    const errorPath = join(RESULTS_DIR, `${jobId}.error`);
    const errorText = existsSync(errorPath) ? readFileSync(errorPath, "utf-8") : "Unknown error";

    return res.status(500).json({ error: errorText });
  }

  const resultPath = join(RESULTS_DIR, `${jobId}.txt`);
  if (!existsSync(resultPath)) {
    return res.status(500).json({ error: "Result file missing" });
  }

  res.type("text/plain").send(readFileSync(resultPath, "utf-8"));
});

app.get("/health", (_req, res) => {
  res.json({ status: "ok" });
});

app.listen(PORT, () => {
  console.log(`WhisperRoles API listening on port ${PORT}`);
  console.log(`Results dir: ${RESULTS_DIR}`);
});
