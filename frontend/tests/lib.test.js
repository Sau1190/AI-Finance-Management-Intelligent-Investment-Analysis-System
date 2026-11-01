// Run with: npm test   (Node's built-in test runner; no extra packages needed)
import test from "node:test";
import assert from "node:assert/strict";
import { fmtNum, fmtPct, fmtBytes, fmtDateTime, labelize, isValidSymbol, cleanSymbol, parseLines, fmtRiskValue, parseWeights } from "../src/lib/format.js";
import { ApiError, describeError, isNotFound, toApiError } from "../src/lib/errors.js";
import { buildPaths, niceExtent } from "../src/lib/chart.js";
import { SAMPLE_CSV, SAMPLE_HEADLINES, DISCLAIMER } from "../src/lib/sample.js";

test("number formatting never invents values", () => {
  assert.equal(fmtNum(1234.5, 2), "1,234.50");
  assert.equal(fmtNum(null), "—");
  assert.equal(fmtNum(undefined), "—");
  assert.equal(fmtNum(NaN), "—");
  assert.equal(fmtNum("5"), "—"); // strings are not silently coerced
  assert.equal(fmtPct(0.1234), "12.34%");
  assert.equal(fmtPct(-0.25, 1), "-25.0%");
  assert.equal(fmtPct(null), "—");
  assert.equal(fmtBytes(2048), "2.0 KB");
  assert.equal(fmtBytes(5), "5 B");
  assert.equal(fmtBytes(-1), "—");
  assert.equal(fmtDateTime("2025-01-10T08:30:00+00:00"), "2025-01-10 08:30 UTC");
  assert.equal(fmtDateTime(null), "—");
  assert.equal(labelize("no_signal"), "No signal");
});

test("symbol validation mirrors the backend rule", () => {
  for (const ok of ["AAA", "aapl", "BRK.B", "BF-B", "A", "ABCDEFGHIJ"]) assert.ok(isValidSymbol(ok), ok);
  for (const bad of ["", "ABCDEFGHIJK", "A B", "A/B", "../x", "A?x=1", "é", "<script>"]) assert.ok(!isValidSymbol(bad), bad);
  assert.equal(cleanSymbol("  aapl "), "AAPL");
});

test("parseLines drops blanks and trims", () => {
  assert.deepEqual(parseLines("a\n\n  b  \r\nc"), ["a", "b", "c"]);
  assert.deepEqual(parseLines(""), []);
});

test("risk values: fractions are percentages, beta/correlation are plain", () => {
  assert.equal(fmtRiskValue({ key: "max_drawdown", value: -0.25 }), "-25.00%");
  assert.equal(fmtRiskValue({ key: "beta", value: 1.2345 }), "1.235");
  assert.equal(fmtRiskValue({ key: "beta", value: null }), "—");
  assert.equal(fmtRiskValue(undefined), "—");
});

test("weights: blank means not supplied, bad input is reported", () => {
  assert.deepEqual(parseWeights({ a: "", b: " " }), { weights: null, error: null });
  assert.deepEqual(parseWeights({ a: "2", b: "1.5", c: "" }), { weights: { a: 2, b: 1.5 }, error: null });
  assert.match(parseWeights({ a: "x" }).error, /must be a number/);
  assert.match(parseWeights({ a: "-1" }).error, /0 or more/);
});

test("errors: not-found is empty only for NOT_FOUND 404s", () => {
  assert.ok(isNotFound(new ApiError({ kind: "http", status: 404, code: "SCORE_RESULT_NOT_FOUND" })));
  assert.ok(!isNotFound(new ApiError({ kind: "http", status: 404, code: "FILE_GONE" })));
  assert.ok(!isNotFound(new ApiError({ kind: "http", status: 500, code: "X_NOT_FOUND" })));
  assert.ok(!isNotFound(new Error("boom")));
  assert.equal(toApiError(new Error("secret stack detail")).message, "Something unexpected went wrong in the dashboard.");
});

test("error descriptions give a plain hint and never echo stack text", () => {
  const net = describeError(new ApiError({ kind: "network", message: "The dashboard could not connect to the backend." }));
  assert.match(net.title, /Cannot reach/); assert.match(net.hint, /port 8000/);
  const key = describeError(new ApiError({ kind: "http", status: 503, code: "PROVIDER_NOT_CONFIGURED", message: "No key." }));
  assert.match(key.hint, /backend .env file\), never in this dashboard/);
  assert.match(describeError(new ApiError({ kind: "http", status: 409, code: "SCORE_NOT_COMPLETE", message: "m" })).hint, /did not complete/);
  assert.match(describeError(new ApiError({ kind: "http", status: 404, code: "MARKET_RESULT_NOT_FOUND", message: "m" })).hint, /market data/);
  assert.equal(describeError(new Error("Traceback ...")).message, "Something unexpected went wrong in the dashboard.");
});

test("chart: missing values break the line instead of drawing zero", () => {
  const g = buildPaths([{ name: "s", values: [1, 2, null, 4, 5] }], 760, 240);
  assert.equal((g.paths[0].match(/M/g) || []).length, 2); // two segments
  assert.ok(!/NaN|Infinity/.test(g.paths[0]));
  assert.equal(buildPaths([{ name: "s", values: [null, null] }], 760, 240).extent, null);
  assert.equal(buildPaths([{ name: "s", values: [] }], 760, 240).paths[0], "");
  const flat = niceExtent([5, 5, 5]); assert.ok(flat.max > flat.min);
  const one = buildPaths([{ name: "s", values: [3] }], 760, 240); assert.match(one.paths[0], /^M[\d.]+,[\d.]+$/);
  // higher value is drawn higher on screen (smaller y)
  const up = buildPaths([{ name: "s", values: [1, 9] }], 760, 240);
  const ys = [...up.paths[0].matchAll(/,([\d.]+)/g)].map((m) => Number(m[1]));
  assert.ok(ys[1] < ys[0]);
});

test("sample data is what the docs describe", () => {
  const rows = SAMPLE_CSV.trim().split("\n");
  assert.equal(rows.length, 4); // header + 3 years
  assert.match(rows[0], /^Date,Ticker,Revenue,Net Income,Total Assets,Total Liabilities,Shareholders Equity,Total Debt$/);
  assert.equal(SAMPLE_HEADLINES.split("\n").length, 6);
  assert.match(DISCLAIMER, /not investment advice/i);
  assert.ok(!/api[_-]?key/i.test(SAMPLE_CSV + SAMPLE_HEADLINES));
});
