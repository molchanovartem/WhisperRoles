#!/usr/bin/env node

/**
 * Usage:
 *   node client.mjs <file.mp3> [http://localhost:8000]
 *
 * Uploads an audio file, polls for result, prints transcript.
 */

const [,, filePath, baseUrl = "http://localhost:8000"] = process.argv;

if (!filePath) {
  console.error("Usage: node client.mjs <file.mp3> [http://server:8000]");
  process.exit(1);
}

const fs = await import("node:fs");
const path = await import("node:path");

const fileName = path.default.basename(filePath);
const fileBuffer = fs.default.readFileSync(filePath);
const blob = new Blob([fileBuffer]);

const form = new FormData();
form.append("file", blob, fileName);

console.log(`Uploading ${fileName}...`);

const uploadRes = await fetch(`${baseUrl}/transcribe`, {
  method: "POST",
  body: form,
});

if (!uploadRes.ok) {
  console.error("Upload failed:", await uploadRes.text());
  process.exit(1);
}

const { job_id } = await uploadRes.json();
console.log(`Job ID: ${job_id}`);
console.log("Waiting for result...");

const POLL_INTERVAL = 3000;

while (true) {
  await new Promise((r) => setTimeout(r, POLL_INTERVAL));

  const statusRes = await fetch(`${baseUrl}/status/${job_id}`);
  const { status } = await statusRes.json();

  if (status === "processing") {
    process.stdout.write(".");
    continue;
  }

  console.log();

  if (status === "error") {
    const errRes = await fetch(`${baseUrl}/result/${job_id}`);
    console.error("Error:", await errRes.text());
    process.exit(1);
  }

  if (status === "done") {
    const resultRes = await fetch(`${baseUrl}/result/${job_id}`);
    const transcript = await resultRes.text();
    console.log("\n--- Transcript ---\n");
    console.log(transcript);
    break;
  }
}
