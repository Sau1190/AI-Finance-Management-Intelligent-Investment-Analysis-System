// Pure logic behind the redesigned workspace: navigation, suggested actions, activity, overview tiles.
import test from "node:test";
import assert from "node:assert/strict";
import { NAV_GROUPS, NAV_ITEMS, navItem } from "../src/lib/nav.js";
import { COMPOSER_ACTIONS, OVERVIEW_ACTIONS, resolveAction } from "../src/lib/actions.js";
import { MAX_ACTIVITY, addActivity, timeAgo } from "../src/lib/activity.js";
import { tileFor } from "../src/lib/overview.js";

const csv = { id: "f1", file_type: "csv", original_filename: "a.csv" };
const pdf = { id: "f2", file_type: "pdf", original_filename: "a.pdf" };

test("navigation covers every implemented workflow exactly once", () => {
  const ids = NAV_ITEMS.map((n) => n.id);
  assert.deepEqual(ids, ["overview", "files", "process", "pdf", "fundamentals", "market", "technical", "sentiment", "risk", "score", "explain"]);
  assert.equal(new Set(ids).size, ids.length);
  assert.equal(navItem("nope").id, "overview");
  assert.ok(NAV_GROUPS.every((g) => g.items.every((n) => n.label && n.blurb)));
});

test("the five requested suggested actions exist, with these exact labels", () => {
  assert.deepEqual(COMPOSER_ACTIONS.map((a) => a.label),
    ["Analyze a file", "Check sentiment", "Calculate risk", "Score this company", "Explain the score"]);
  assert.ok(OVERVIEW_ACTIONS.length >= COMPOSER_ACTIONS.length);
});

test("every action resolves to a real page", () => {
  const pages = new Set(NAV_ITEMS.map((n) => n.id));
  for (const a of OVERVIEW_ACTIONS) {
    for (const ctx of [{ file: csv, symbolOk: true }, { file: null, symbolOk: false }]) {
      assert.ok(pages.has(resolveAction(a.id, ctx).tab), `${a.id} -> unknown page`);
    }
  }
});

test("Analyze a file: no file -> Files with a note; PDF -> extraction; table -> processing", () => {
  const none = resolveAction("analyze-file", { file: null, symbolOk: true });
  assert.equal(none.tab, "files"); assert.equal(none.intent, null); assert.match(none.note, /file first/);
  assert.deepEqual(resolveAction("analyze-file", { file: pdf, symbolOk: true }), { tab: "pdf", intent: "run-extraction", note: null });
  assert.equal(resolveAction("analyze-file", { file: csv, symbolOk: false }).intent, "run-processing");
});

test("symbol-based actions start their workflow only with a valid symbol", () => {
  const want = { risk: "run-risk", score: "run-score", technical: "run-technical", explain: "load-explanation", sentiment: "focus-headlines" };
  for (const [id, intent] of Object.entries(want)) {
    assert.equal(resolveAction(id, { symbolOk: true }).intent, intent, id);
    const bad = resolveAction(id, { symbolOk: false });
    assert.equal(bad.intent, null, `${id} must not start without a symbol`); assert.match(bad.note, /valid symbol/);
  }
});

test("actions that spend provider quota never start automatically", () => {
  const r = resolveAction("market", { file: csv, symbolOk: true });
  assert.equal(r.tab, "market"); assert.equal(r.intent, null);
  const intents = OVERVIEW_ACTIONS.map((a) => resolveAction(a.id, { file: csv, symbolOk: true }).intent);
  assert.ok(!intents.some((i) => /market|news|fetch/.test(i || "")));
});

test("Run fundamentals needs a table file", () => {
  assert.equal(resolveAction("fundamentals", { file: csv }).intent, "run-fundamentals");
  assert.equal(resolveAction("fundamentals", { file: pdf }).intent, null);
  assert.equal(resolveAction("fundamentals", { file: null }).tab, "files");
});

test("activity: newest first, capped, repeats collapse, errors kept distinct", () => {
  const t0 = new Date("2025-01-10T12:00:00Z");
  let list = [];
  for (let i = 0; i < MAX_ACTIVITY + 5; i++) list = addActivity(list, { label: `step ${i}`, tab: "score" }, t0);
  assert.equal(list.length, MAX_ACTIVITY); assert.equal(list[0].label, `step ${MAX_ACTIVITY + 4}`);
  list = addActivity(list, { label: "same", tab: "risk" }, t0); list = addActivity(list, { label: "same", tab: "risk" }, t0);
  assert.equal(list.filter((a) => a.label === "same").length, 1);
  list = addActivity(list, { label: "same", tab: "risk", status: "error" }, t0);
  assert.equal(list.filter((a) => a.label === "same").length, 2);
  assert.equal(new Set(list.map((a) => a.id)).size, list.length);
});

test("timeAgo is readable", () => {
  const now = new Date("2025-01-10T12:00:00Z");
  assert.equal(timeAgo("2025-01-10T11:59:58Z", now), "just now");
  assert.equal(timeAgo("2025-01-10T11:59:00Z", now), "1 min ago");
  assert.equal(timeAgo("2025-01-10T09:00:00Z", now), "3 h ago");
  assert.equal(timeAgo("2025-01-08T12:00:00Z", now), "2 d ago");
});

test("overview tiles: empty, error, failed and ready states", () => {
  assert.equal(tileFor("risk", { status: "empty" }).value, "Not run yet");
  assert.equal(tileFor("risk", { status: "loading" }).state, "loading");
  assert.notEqual(tileFor("risk", { status: "idle" }).value, "Loading…", "an idle (never requested) tile must not look like it is loading forever");
  assert.equal(tileFor("risk", { status: "error", error: { message: "boom" } }).note, "boom");
  assert.equal(tileFor("risk", { status: "success", data: { status: "FAILED", error_message: "x" } }).state, "failed");
  const risk = tileFor("risk", { status: "success", data: { status: "COMPLETE", metrics: [{ key: "annualized_volatility", value: 0.2 }] } });
  assert.deepEqual([risk.state, risk.value], ["ready", "20.00%"]);
  const sent = tileFor("sentiment", { status: "success", data: { status: "COMPLETE", mean_score: 0.5, label: "positive", scored_count: 6, text_count: 6 } });
  assert.equal(sent.value, "0.50"); assert.match(sent.note, /6 of 6/);
  assert.equal(tileFor("sentiment", { status: "success", data: { status: "COMPLETE", mean_score: null, label: "no_signal" } }).value, "no signal");
  const f = tileFor("fundamental", { status: "success", data: { status: "COMPLETE", worksheets: [{ metrics: [{ status: "COMPUTED" }, { status: "NOT_COMPUTABLE" }] }] } });
  assert.equal(f.value, "1 of 2 ratios");
});

test("no advice wording in any suggested-action or navigation text", () => {
  const text = [...OVERVIEW_ACTIONS.map((a) => a.label), ...NAV_ITEMS.flatMap((n) => [n.label, n.blurb])].join(" ");
  assert.doesNotMatch(text, /\b(buy|sell|hold|recommend|invest|predict|ask (me|ai|anything)|chat with)\b/i);
});
