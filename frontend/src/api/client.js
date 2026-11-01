// The only place the dashboard talks to the backend. It holds NO secrets:
// market-data and news API keys live in the server's .env and are never sent
// to, or stored in, the browser. In development Vite proxies /api to the backend.
import { ApiError } from "../lib/errors.js";

const API_BASE = import.meta.env?.VITE_API_BASE || "";
const enc = encodeURIComponent;

// A hung backend must not leave a spinner forever. Market/news fetches call an
// outside provider (server-side timeout 10 s), uploads and downloads move files.
export const DEFAULT_TIMEOUT_MS = 30_000;
export const LONG_TIMEOUT_MS = 120_000;

async function request(path, { method = "GET", json, form, blob = false, timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  const init = { method, headers: {} };
  if (json !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(json);
  } else if (form) {
    init.body = form; // the browser sets the multipart boundary itself
  }
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  if (controller) init.signal = controller.signal;
  let timedOut = false;
  const timer = controller
    ? setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs)
    : null;
  let response;
  try {
    response = await fetch(`${API_BASE}/api${path}`, init);
  } catch {
    if (timer) clearTimeout(timer);
    if (timedOut) {
      throw new ApiError({
        kind: "timeout",
        message: "The backend did not answer in time.",
      });
    }
    throw new ApiError({
      kind: "network",
      message: "The dashboard could not connect to the backend.",
    });
  }
  // Headers arrived; the body is read below. Keep the timer for the body read too.
  try {
    return await readResponse(response, { blob });
  } catch (e) {
    if (e instanceof ApiError) throw e;
    if (timedOut) throw new ApiError({ kind: "timeout", message: "The backend did not answer in time." });
    throw new ApiError({ kind: "http", status: response.status, code: "INVALID_RESPONSE", message: "The backend sent an answer the dashboard could not read." });
  } finally {
    if (timer) clearTimeout(timer);
  }
}

async function readResponse(response, { blob }) {
  if (!response.ok) {
    let code = "";
    let message = `The backend answered with status ${response.status}.`;
    try {
      const body = await response.json();
      const d = body && body.detail;
      if (d && typeof d === "object" && !Array.isArray(d)) {
        code = d.code || "";
        message = d.message || message;
      } else if (typeof d === "string") {
        message = d;
      }
    } catch {
      /* keep the generic message */
    }
    throw new ApiError({ kind: "http", status: response.status, code, message });
  }
  // A success status with a body that is not JSON (e.g. a proxy's HTML page)
  // is reported plainly instead of surfacing a parser error.
  return blob ? response.blob() : response.json();
}

// Health
export const getHealth = () => request("/health");

// Files (Phase 1)
export const listFiles = () => request("/files");
export function uploadFile(file) {
  const form = new FormData();
  form.append("file", file, file.name);
  return request("/files", { method: "POST", form, timeoutMs: LONG_TIMEOUT_MS });
}

// Excel / CSV (Phases 2-3) and PDF (Phase 4), Fundamentals (Phase 5) — all per file
export const runProcessing = (id) => request(`/files/${enc(id)}/process`, { method: "POST" });
export const getProcessing = (id) => request(`/files/${enc(id)}/process`);
export const runExport = (id) => request(`/files/${enc(id)}/export`, { method: "POST" });
export const getExport = (id) => request(`/files/${enc(id)}/export`);
export const downloadExport = (id) => request(`/files/${enc(id)}/export/download`, { blob: true, timeoutMs: LONG_TIMEOUT_MS });
export const runExtraction = (id) => request(`/files/${enc(id)}/extract`, { method: "POST" });
export const getExtraction = (id) => request(`/files/${enc(id)}/extract`);
export const runFundamentals = (id) => request(`/files/${enc(id)}/fundamentals`, { method: "POST" });
export const getFundamentals = (id) => request(`/files/${enc(id)}/fundamentals`);

// Market data (Phase 6)
export const fetchMarket = (symbol, history = "compact") =>
  request(`/market-data/${enc(symbol)}?history=${enc(history)}`, { method: "POST", timeoutMs: LONG_TIMEOUT_MS });
export const getMarket = (symbol) => request(`/market-data/${enc(symbol)}`);
export const getPrices = (symbol, limit = 250) => request(`/market-data/${enc(symbol)}/prices?limit=${limit}`);

// Technical (Phase 7)
export const runTechnical = (symbol) => request(`/technical/${enc(symbol)}`, { method: "POST" });
export const getTechnical = (symbol) => request(`/technical/${enc(symbol)}`);
export const getTechnicalSeries = (symbol, limit = 250) => request(`/technical/${enc(symbol)}/series?limit=${limit}`);

// Sentiment (Phase 8)
export const scoreTexts = (symbol, texts) => request(`/sentiment/${enc(symbol)}/text`, { method: "POST", json: { texts } });
export const fetchNews = (symbol, query) =>
  request(`/sentiment/${enc(symbol)}/news${query ? `?query=${enc(query)}` : ""}`, { method: "POST", timeoutMs: LONG_TIMEOUT_MS });
export const getSentiment = (symbol) => request(`/sentiment/${enc(symbol)}`);

// Risk (Phase 9)
export const runRisk = (symbol, benchmark) =>
  request(`/risk/${enc(symbol)}${benchmark ? `?benchmark=${enc(benchmark)}` : ""}`, { method: "POST" });
export const getRisk = (symbol) => request(`/risk/${enc(symbol)}`);

// Scoring (Phase 10) and explanation (Phase 11)
export const runScore = (symbol, body) => request(`/scores/${enc(symbol)}`, { method: "POST", json: body || {} });
export const getScore = (symbol) => request(`/scores/${enc(symbol)}`);
export const getScoringMethod = () => request("/scoring-method");
export const getExplanation = (symbol) => request(`/scores/${enc(symbol)}/explanation`);

// Save a Blob as a file in the browser.
export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "download";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
