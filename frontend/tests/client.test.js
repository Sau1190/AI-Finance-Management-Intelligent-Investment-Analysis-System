// The API client with a fake fetch: URL/method/body shape, error mapping, no secrets.
import test from "node:test";
import assert from "node:assert/strict";
import * as api from "../src/api/client.js";
import { ApiError } from "../src/lib/errors.js";

function fakeFetch(handler) {
  const calls = [];
  globalThis.fetch = async (url, init = {}) => { calls.push({ url, init }); return handler(url, init); };
  return calls;
}
const json = (status, body) => ({ ok: status < 400, status, json: async () => body, blob: async () => new Blob(["x"]) });

test("GET/POST URLs and encoding", async () => {
  const calls = fakeFetch(() => json(200, {}));
  await api.getHealth();
  await api.fetchMarket("BRK.B", "full");
  await api.runRisk("AAA", "SPY");
  await api.runRisk("AAA", "");
  await api.fetchNews("AAA", "apple inc & co");
  await api.getPrices("A B", 50);
  await api.runProcessing("id/../x");
  const urls = calls.map((c) => `${c.init.method || "GET"} ${c.url}`);
  assert.deepEqual(urls, [
    "GET /api/health",
    "POST /api/market-data/BRK.B?history=full",
    "POST /api/risk/AAA?benchmark=SPY",
    "POST /api/risk/AAA",
    "POST /api/sentiment/AAA/news?query=apple%20inc%20%26%20co",
    "GET /api/market-data/A%20B/prices?limit=50",
    "POST /api/files/id%2F..%2Fx/process",
  ]);
});

test("JSON bodies and multipart upload", async () => {
  const calls = fakeFetch(() => json(201, {}));
  await api.scoreTexts("AAA", ["a", "b"]);
  await api.runScore("AAA", { file_id: "f1", weights: { risk: 2 } });
  await api.runScore("AAA");
  assert.equal(calls[0].init.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(calls[0].init.body), { texts: ["a", "b"] });
  assert.deepEqual(JSON.parse(calls[1].init.body), { file_id: "f1", weights: { risk: 2 } });
  assert.deepEqual(JSON.parse(calls[2].init.body), {});
  await api.uploadFile(new File(["a,b\n1,2"], "t.csv", { type: "text/csv" }));
  const up = calls[3];
  assert.ok(up.init.body instanceof FormData && up.init.body.get("file").name === "t.csv");
  assert.equal(up.init.headers["Content-Type"], undefined); // browser sets the boundary
});

test("error envelope is parsed; framework errors and network failures are mapped", async () => {
  fakeFetch(() => json(404, { detail: { code: "SCORE_RESULT_NOT_FOUND", message: "No score yet." } }));
  await assert.rejects(api.getScore("AAA"), (e) => e instanceof ApiError && e.status === 404 && e.code === "SCORE_RESULT_NOT_FOUND" && e.message === "No score yet.");
  fakeFetch(() => json(422, { detail: [{ loc: ["body"], msg: "internal pydantic text" }] }));
  await assert.rejects(api.getScore("AAA"), (e) => e.status === 422 && !/pydantic/.test(e.message));
  fakeFetch(() => ({ ok: false, status: 500, json: async () => { throw new Error("not json"); } }));
  await assert.rejects(api.getScore("AAA"), (e) => e.status === 500 && /status 500/.test(e.message));
  fakeFetch(() => { throw new TypeError("fetch failed"); });
  await assert.rejects(api.getScore("AAA"), (e) => e.kind === "network" && !/fetch failed/.test(e.message));
});

test("client source contains no API keys or secrets", async () => {
  const { readFileSync, readdirSync, statSync } = await import("node:fs");
  const { join } = await import("node:path");
  const walk = (d) => readdirSync(d).flatMap((f) => (statSync(join(d, f)).isDirectory() ? walk(join(d, f)) : [join(d, f)]));
  for (const f of walk(new URL("../src", import.meta.url).pathname)) {
    const t = readFileSync(f, "utf8");
    assert.ok(!/(ALPHA_VANTAGE|NEWS_API|LLM_API)_KEY\s*[=:]/.test(t), `${f}: key assignment`);
    assert.ok(!/localStorage|sessionStorage/.test(t), `${f}: uses browser storage`);
    assert.ok(!/apikey=|api_key=/i.test(t), `${f}: key in a URL`);
  }
});
