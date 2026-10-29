import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Who } from "@desert-ant-labs/who/native";

const PORT = Number(process.env.WHO_PORT || 8090);
const HOST = process.env.WHO_HOST || "127.0.0.1";
const MODEL_DIR = process.env.WHO_MODEL_DIR || path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "models", "who");
const MIN_SHARE = Number(process.env.WHO_MIN_SHARE || 0);

const who = await Who.load({ directory: MODEL_DIR });
let queue = Promise.resolve();

function diarize(bytes) {
  const job = queue.then(() => who.diarize(bytes));
  queue = job.catch(() => {});
  return job;
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

function send(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

const server = http.createServer(async (req, res) => {
  try {
    if (req.method === "GET" && req.url === "/health") {
      return send(res, 200, { ok: true, downloaded: who.isDownloaded(), min_share: MIN_SHARE });
    }
    if (req.method === "POST" && req.url === "/diarize") {
      const body = await readBody(req);
      if (!body.length) return send(res, 400, { error: "empty body, send a 16 kHz mono WAV" });
      const started = performance.now();
      let result = await diarize(new Uint8Array(body));
      if (MIN_SHARE > 0) result = result.keepingSpeakers({ minimumShare: MIN_SHARE });
      return send(res, 200, {
        duration: result.duration,
        speaker_count: result.speakerCount,
        seconds: (performance.now() - started) / 1000,
        turns: result.turns.map((t) => ({ speaker: t.speaker, start: t.start, end: t.end })),
      });
    }
    send(res, 404, { error: "not found" });
  } catch (error) {
    send(res, 500, { error: String(error?.message || error) });
  }
});

server.listen(PORT, HOST, () => console.log(`who engine on http://${HOST}:${PORT}, models in ${MODEL_DIR}`));
