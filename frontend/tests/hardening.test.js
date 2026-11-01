// Phase 14: timeouts, unreadable answers, crash messages, and "no secrets in the browser".
import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import * as api from "../src/api/client.js";
import { ApiError, describeError } from "../src/lib/errors.js";
import { CRASH_MESSAGE, CRASH_TITLE, crashLogLine } from "../src/lib/crash.js";

// A fetch that never answers on its own but honours AbortController, like a real one.
function hangingFetch() {
  globalThis.fetch = (_url, init = {}) =>
    new Promise((_resolve, reject) => {
      init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    });
}
const reply = (status, bodyFn) => ({ ok: status < 400, status, json: bodyFn, blob: async () => new Blob(["x"]) });

test("timeouts are sane: default is seconds-scale, uploads/provider calls get longer", () => {
  assert.ok(api.DEFAULT_TIMEOUT_MS >= 5_000 && api.DEFAULT_TIMEOUT_MS <= 60_000);
  assert.ok(api.LONG_TIMEOUT_MS > api.DEFAULT_TIMEOUT_MS);
});

test("timeout: the abort is turned into a plain ApiError of kind 'timeout'", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  hangingFetch();
  const pending = api.getHealth();
  const settled = assert.rejects(pending, (e) => e instanceof ApiError && e.kind === "timeout" && !/abort/i.test(e.message));
  t.mock.timers.tick(api.DEFAULT_TIMEOUT_MS + 1);
  await settled;
});

test("uploads and provider fetches get the longer timeout", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  hangingFetch();
  let state = "pending";
  const upload = api.uploadFile(new File(["a,b\n1,2"], "t.csv", { type: "text/csv" })).catch((e) => { state = e.kind; });
  t.mock.timers.tick(api.DEFAULT_TIMEOUT_MS + 1);
  await new Promise((r) => setImmediate(r));
  assert.equal(state, "pending"); // still waiting after the default timeout
  t.mock.timers.tick(api.LONG_TIMEOUT_MS);
  await upload;
  assert.equal(state, "timeout");
});

test("a successful answer that is not JSON becomes a readable error, with no parser text", async () => {
  globalThis.fetch = async () => reply(200, async () => { throw new SyntaxError("Unexpected token < in JSON at position 0"); });
  await assert.rejects(api.getHealth(), (e) =>
    e instanceof ApiError && e.code === "INVALID_RESPONSE" && !/token|JSON|position/i.test(e.message));
});

test("a finished request does not leave a timer running", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  globalThis.fetch = async () => reply(200, async () => ({ ok: true }));
  assert.deepEqual(await api.getHealth(), { ok: true });
  t.mock.timers.tick(api.LONG_TIMEOUT_MS * 2); // nothing should fire or throw
});

test("describeError: timeouts and database failures get their own plain hints", () => {
  const timeout = describeError(new ApiError({ kind: "timeout", message: "The backend did not answer in time." }));
  assert.match(timeout.title, /too long/);
  const db = describeError(new ApiError({ kind: "http", status: 503, code: "DATABASE_FAILURE", message: "m" }));
  assert.match(db.hint, /database/i);
  assert.doesNotMatch(db.hint, /API key/); // a database outage is not a missing-key problem
  const key = describeError(new ApiError({ kind: "http", status: 503, code: "PROVIDER_NOT_CONFIGURED", message: "m" }));
  assert.match(key.hint, /API key/);
  assert.match(describeError(new ApiError({ kind: "http", status: 500, code: "INTERNAL_ERROR", message: "m" })).hint, /unexpected/i);
});

test("crash screen text is fixed and the log line carries only the error type", () => {
  const secretError = new TypeError("cannot read 'balance' of ACME-secret-row");
  const line = crashLogLine(secretError);
  assert.equal(line, "Dashboard page crashed while rendering: TypeError");
  assert.ok(!line.includes("ACME") && !line.includes("balance"));
  assert.equal(crashLogLine(null), "Dashboard page crashed while rendering: Error");
  assert.ok(CRASH_TITLE && CRASH_MESSAGE && !/stack|trace/i.test(CRASH_MESSAGE));
});

test("both the app shell and each page are wrapped in the error boundary", () => {
  const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
  assert.match(read("main.jsx"), /<ErrorBoundary>\s*<App \/>\s*<\/ErrorBoundary>/);
  assert.match(read("App.jsx"), /<ErrorBoundary key=\{tab\}>\s*<Page \/>\s*<\/ErrorBoundary>/);
});

test("no API key, secret or browser storage appears anywhere in the dashboard source", () => {
  const files = [];
  (function walk(dir) {
    for (const name of readdirSync(dir)) {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) walk(path);
      else if (/\.(js|jsx)$/.test(name)) files.push(path);
    }
  })(new URL("../src", import.meta.url).pathname);
  assert.ok(files.length > 20);
  for (const file of files) {
    const src = readFileSync(file, "utf8");
    assert.doesNotMatch(src, /localStorage|sessionStorage|indexedDB|document\.cookie/, file);
    assert.doesNotMatch(src, /dangerouslySetInnerHTML|\beval\(|new Function\(/, file);
    assert.doesNotMatch(src, /VITE_[A-Z_]*(KEY|SECRET|TOKEN)/, file);
    assert.doesNotMatch(src, /api[_-]?key\s*[:=]\s*["'][^"']+["']/i, file);
  }
  const base = readFileSync(new URL("../src/api/client.js", import.meta.url), "utf8");
  assert.doesNotMatch(base, /Authorization|X-Api-Key/i);
});
