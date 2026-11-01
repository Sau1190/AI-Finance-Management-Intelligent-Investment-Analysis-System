// Browser test for the dashboard. NOT part of `npm test` (needs Playwright + Chromium).
//   node e2e/run-e2e.mjs        (from frontend/, after: python e2e/make_fixtures.py)
// It bundles the real dashboard source, serves it with the mock API (mock-api.mjs), and
// drives a real headless browser. It does NOT talk to the real backend.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { startMock } from "./mock-api.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const GLOBAL = process.env.NODE_PATH || "/home/claude/.npm-global/lib/node_modules";
const require = createRequire(GLOBAL + "/");
const { chromium } = require("playwright");
const esbuild = process.env.ESBUILD || path.join(GLOBAL, "tsx/node_modules/esbuild/bin/esbuild");

// ---- build (development mode, like `npm run dev`, so React StrictMode + warnings are active)
const dist = path.join(root, ".e2e-dist");
fs.rmSync(dist, { recursive: true, force: true }); fs.mkdirSync(dist, { recursive: true });
execFileSync(esbuild, ["src/main.jsx", "--bundle", "--format=esm", "--jsx=automatic", "--outfile=" + path.join(dist, "app.js"),
  '--define:process.env.NODE_ENV="development"', "--log-level=warning"], { cwd: root, env: { ...process.env, NODE_PATH: GLOBAL }, stdio: "inherit" });
fs.writeFileSync(path.join(dist, "index.html"), '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/app.css"></head><body><div id="root"></div><script type="module" src="/app.js"></script></body></html>');

const PORT = 18765, BASE = `http://127.0.0.1:${PORT}`;
const F = JSON.parse(fs.readFileSync(path.join(here, "fixtures.json"), "utf8"));
const mock = await startMock({ port: PORT, distDir: dist });
const control = (flags) => fetch(`${BASE}/__control`, { method: "POST", body: JSON.stringify(flags) });
const reset = () => fetch(`${BASE}/__reset`);

const browser = await chromium.launch();
const results = []; const consoleProblems = []; const requests = [];
const shots = "/tmp/e2e-shots"; fs.mkdirSync(shots, { recursive: true });

async function newPage(viewport = { width: 1280, height: 900 }) {
  const ctx = await browser.newContext({ viewport, acceptDownloads: true });
  const page = await ctx.newPage();
  page.on("console", (m) => { if (["error", "warning"].includes(m.type())) consoleProblems.push(`${m.type()}: ${m.text()}`); });
  page.on("pageerror", (e) => consoleProblems.push("pageerror: " + e.message));
  page.on("request", (r) => requests.push({ url: r.url(), headers: r.headers() }));
  return page;
}
async function step(name, fn) {
  try { await fn(); results.push([true, name]); console.log("PASS", name); }
  catch (e) { await page.screenshot({ path: `${shots}/FAIL-${results.length}.png`, fullPage: true }).catch(() => {}); results.push([false, name, e.message.split("\n")[0]]); console.log("FAIL", name, "\n   ", e.message.split("\n").slice(0, 3).join("\n    ")); }
}
const ok = (c, m) => { if (!c) throw new Error(m); };
const tab = (page, name) => page.getByRole("navigation").getByRole("button", { name }).click();
const chip = (page, name) => page.getByRole("group", { name: "Suggested actions" }).getByRole("button", { name }).click();
const logOf = async () => (await (await fetch(`${BASE}/__log`)).json());
const count = (log, re) => log.filter((l) => re.test(l)).length;
const visible = (page, text, t = 5000) => page.getByText(text, { exact: false }).first().waitFor({ state: "visible", timeout: t });
const weight = (page, name) => page.getByRole("spinbutton", { name, exact: true });
const fmt1 = (v) => v.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

// ------------------------------------------------------------------ 1. Home, health, disclaimer, navigation
await reset();
let page = await newPage();
await page.goto(BASE);
await step("Home: backend status shows connected + disclaimer visible", async () => {
  await visible(page, "connected");
  ok(await page.getByTestId("disclaimer").first().isVisible(), "disclaimer not visible");
  await visible(page, "not investment advice");
});
await step("Disclaimer is present on every tab", async () => {
  for (const name of ["Overview", "Files", "Process", "PDF", "Fundamentals", "Market", "Technical", "Sentiment", "Risk", "Score", "Explain"]) {
    await tab(page, name);
    ok(await page.locator(".sticky-disclaimer").getByTestId("disclaimer").isVisible(), `no pinned disclaimer on ${name}`);
  }
  await tab(page, "Overview");
});
await step("Header disclaimer still visible after scrolling (page scrolled to bottom shows footer copy)", async () => {
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  ok(await page.getByTestId("disclaimer").last().isVisible(), "footer disclaimer hidden");
});

await step("Workspace layout: sidebar (11 pages, recent activity), five suggested actions, honest not-a-chatbot hint", async () => {
  const links = await page.getByRole("navigation").getByRole("button").allInnerTexts();
  ok(links.length === 11, "expected 11 sidebar pages, got " + links.length + ": " + links.join(","));
  await visible(page, "Nothing yet. Things you run this session appear here.");
  const chips = await page.getByRole("group", { name: "Suggested actions" }).getByRole("button").allInnerTexts();
  ok(JSON.stringify(chips.map((c) => c.trim())) === JSON.stringify(["Analyze a file", "Check sentiment", "Calculate risk", "Score this company", "Explain the score"]), "chips: " + chips.join("|"));
  await visible(page, "not a chatbot");
  const all = await page.locator("body").innerText();
  ok(!/\b(ask me anything|ai assistant|chat with|ai-generated|generated by ai)\b/i.test(all), "implies chat/AI answers");
});
await step("Overview: empty score hero and 'not run yet' tiles when nothing exists", async () => {
  await visible(page, "No score yet for AAA");
  ok((await page.getByText("Not run yet").count()) >= 4, "expected empty tiles");
  ok(await page.getByRole("button", { name: "Load the sample company" }).isVisible(), "sample button missing");
});

// ------------------------------------------------------------------ 2. empty states
await step("Empty states: files, fundamentals, score, explain", async () => {
  await tab(page, "Files"); await visible(page, "No files uploaded yet");
  await tab(page, "Fundamentals"); await visible(page, "Choose or upload a file first");
  await tab(page, "Score"); await visible(page, "No score yet for this symbol");
  await tab(page, "Explain"); await visible(page, "has no score yet");
});

await step("Suggested action 'Analyze a file' with no file opens Files and explains what to do", async () => {
  await tab(page, "Overview");
  await chip(page, "Analyze a file");
  await visible(page, "Choose or upload a file first, then run this action again");
  ok((await page.getByRole("navigation").getByRole("button", { name: "Files" }).getAttribute("aria-current")) === "page", "Files not active");
  await page.getByRole("button", { name: "Dismiss" }).click();
});

// ------------------------------------------------------------------ 3. loading state
await step("Loading state is shown while a request is slow", async () => {
  await control({ slowMs: 1200 });
  await tab(page, "Files");
  await page.getByRole("button", { name: "Refresh" }).click();
  await page.getByRole("status").first().waitFor({ state: "visible", timeout: 2000 });
  await page.getByText("No files uploaded yet").waitFor({ state: "visible", timeout: 5000 });
  await control({ slowMs: 0 });
});

// ------------------------------------------------------------------ 4. keyless demo path
await step("Upload: built-in sample CSV is uploaded and selected", async () => {
  await page.getByRole("button", { name: /Create & upload the sample CSV/ }).click();
  await visible(page, "Uploaded “sample_financials_AAA.csv”");
  ok((await page.getByTestId("selected-file").innerText()).includes("sample_financials_AAA.csv (CSV)"), "file not selected in header");
  await visible(page, "Use this file", 1000).catch(() => {}); // list refresh
  await page.getByText("Selected").first().waitFor({ state: "visible", timeout: 3000 });
});
await step("Process: run processing, see columns + standard concepts; generate + download report", async () => {
  await tab(page, "Process");
  await visible(page, "has not been processed yet");
  await page.getByRole("button", { name: "Run processing" }).click();
  await visible(page, "Shareholders Equity"); await visible(page, "equity");
  await page.getByRole("button", { name: "Generate report" }).click();
  await visible(page, "sample_financials_AAA_report.xlsx");
  const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download .xlsx" }).click()]);
  ok(dl.suggestedFilename() === "sample_financials_AAA_report.xlsx", "wrong download name " + dl.suggestedFilename());
  await visible(page, "Download started");
});
await step("Fundamentals: run; computed and not-computable metrics both explained", async () => {
  await tab(page, "Fundamentals");
  await page.getByRole("button", { name: "Run fundamentals" }).click();
  await visible(page, "Net profit margin"); await visible(page, "Debt to equity");
  await visible(page, "profit column not found");
  ok((await page.locator("table .badge.ok").count()) >= 5, "expected COMPUTED badges");
});
await step("Suggested action 'Analyze a file' runs processing by itself and shows the result", async () => {
  const before = count(await logOf(), /^POST \/api\/files\/file-1\/process/);
  await chip(page, "Analyze a file");
  await visible(page, "Shareholders Equity");
  const after = count(await logOf(), /^POST \/api\/files\/file-1\/process/);
  ok(after === before + 1, `expected exactly one new processing call, got ${after - before}`);
  await visible(page, "Processed sample_financials_AAA.csv");
});
await step("Sentiment: sample headlines -> real engine result with per-word evidence", async () => {
  await tab(page, "Sentiment");
  await visible(page, "No sentiment result for this symbol yet");
  ok(await page.getByRole("button", { name: "Score these headlines" }).isDisabled(), "score button should be disabled with no text");
  await page.getByRole("button", { name: "Use sample headlines" }).click();
  await visible(page, "6 headline(s)");
  await page.getByRole("button", { name: "Score these headlines" }).click();
  await visible(page, "6 / 6");
  await page.getByText("Each text and the words behind its score").click();
  await visible(page, "record revenue (+2)");
  await visible(page, "averages can hide disagreement");
});
await step("Suggested action 'Check sentiment' opens the page with the headlines box focused; activity is listed", async () => {
  await tab(page, "Overview");
  await chip(page, "Check sentiment");
  await page.getByRole("heading", { name: "Sentiment" }).first().waitFor({ state: "visible" });
  await page.waitForFunction(() => document.activeElement && document.activeElement.tagName === "TEXTAREA", null, { timeout: 3000 });
  const act = await page.getByRole("region", { name: "Recent activity" }).innerText();
  ok(/Uploaded sample_financials_AAA\.csv/.test(act) && /Scored 6 headline\(s\) for AAA/.test(act) && /Fundamentals for/.test(act), "activity list incomplete: " + act);
});
let scoreText;
await step("Score: fundamentals + sentiment -> overall score; unavailable components explained", async () => {
  await tab(page, "Score");
  await page.getByRole("button", { name: "Run score" }).click();
  await visible(page, fmt1(F.score_default.overall.score));
  await visible(page, "No successful technical analysis exists");
  await visible(page, "Educational", 1000).catch(() => {});
  scoreText = await page.locator("main").innerText();
  ok(/Overall score \(0–100\)/.test(scoreText), "missing overall label");
  ok(!/\b(buy|sell|hold)\b/i.test(scoreText.replace(/not a recommendation to buy, sell or hold/i, "").replace(/no buy\/sell\/hold labels/ig, "")), "advice wording in score page");
});
await step("Score: scoring method can be shown (rules + limits)", async () => {
  await page.getByRole("button", { name: "Show the scoring method" }).click();
  await visible(page, "Limits");
  await visible(page, "illustrative");
});
await step("Overview shows the saved results: score ring, sentiment tile, fundamentals tile; technical still 'not run yet'", async () => {
  await tab(page, "Overview");
  await page.getByTestId("score-ring").waitFor({ state: "visible" });
  await visible(page, fmt1(F.score_default.overall.score));
  await visible(page, "0.50"); await visible(page, "ratios");
  ok((await page.getByText("Not run yet").count()) >= 2, "technical/risk tiles should be empty");
});
await step("Suggested actions 'Score this company' and 'Explain the score' run the real endpoints", async () => {
  const before = count(await logOf(), /^POST \/api\/scores\/AAA/);
  await chip(page, "Score this company");
  await visible(page, "Overall score (0–100)");
  await visible(page, fmt1(F.score_default.overall.score));
  ok(count(await logOf(), /^POST \/api\/scores\/AAA/) === before + 1, "score was not run exactly once");
  const body = await page.locator("main").innerText();
  ok(/No successful technical analysis exists/.test(body), "unavailable component not explained");
  await chip(page, "Explain the score");
  await page.getByTestId("what").waitFor({ state: "visible" });
  ok(count(await logOf(), /^GET \/api\/scores\/AAA\/explanation/) >= 1, "explanation endpoint not called");
});
await step("Explain: What / How / Why sections with arithmetic cross-check", async () => {
  await tab(page, "Explain");
  await page.getByTestId("what").waitFor({ state: "visible" });
  ok((await page.getByTestId("what").innerText()).includes(`${F.expl_default.what.overall_score.toFixed(1)} out of 100`), "what summary lacks score");
  ok((await page.getByTestId("how").innerText()).includes("matches the stored"), "how lacks arithmetic check");
  const why = await page.getByTestId("why").innerText();
  ok(why.includes("Cost the most points"), "why lacks drivers");
  ok(!/cost 0\.0 points/.test(why), "zero-point driver should be hidden");
  ok(!/Fundamentals: Fundamentals:/.test(await page.getByTestId("how").innerText()), "duplicated component label");
  const all = await page.locator("main").innerText();
  ok(!/\b(recommend|undervalued|overvalued|bullish|bearish)\b/i.test(all.replace(/does not recommend buying[^.]*\./i, "")), "advice wording in explanation");
  await page.screenshot({ path: `${shots}/explain.png`, fullPage: true });
  await page.evaluate(() => window.scrollTo(0, 900)); // well below the top of a long page
  const box = await page.locator(".sticky-disclaimer").boundingBox();
  ok(box && box.y >= 0 && box.y < 5 && box.height > 10, "disclaimer scrolled out of view: " + JSON.stringify(box));
  await page.evaluate(() => window.scrollTo(0, 0));
});
await step("Score with custom weights is stored, shown, and explained", async () => {
  await tab(page, "Score");
  await page.getByText("Custom weights").click();
  const w = F.custom_weights;
  for (const [k, v] of Object.entries(w)) await weight(page, k[0].toUpperCase() + k.slice(1)).fill(String(v));
  await page.getByRole("button", { name: "Run score" }).click();
  await visible(page, "custom"); await visible(page, fmt1(F.score_custom.overall.score));
  await tab(page, "Explain"); await visible(page, "(custom)");
});
await step("Score: invalid weight is caught in the browser (button disabled, message shown)", async () => {
  await tab(page, "Score");
  await page.getByText("Custom weights").click();
  await weight(page, "Risk").fill("-3");
  await visible(page, "must be a number, 0 or more");
  ok(await page.getByRole("button", { name: "Run score" }).isDisabled(), "run should be disabled");
});
await step("Score: backend rejection (all-zero weights) shows the server's message", async () => {
  for (const k of ["Fundamental", "Technical", "Sentiment", "Risk"]) await weight(page, k).fill("0");
  await page.getByRole("button", { name: "Run score" }).click();
  await visible(page, "At least one weight must be above zero");
  await visible(page, "INVALID_WEIGHTS");
});
await step("Explain after a single-component score states plainly that no overall score exists", async () => {
  await reset(); await page.reload();
  await tab(page, "Sentiment");
  await page.getByRole("button", { name: "Use sample headlines" }).click();
  await page.getByRole("button", { name: "Score these headlines" }).click(); await visible(page, "6 / 6");
  await tab(page, "Score"); await page.getByRole("button", { name: "Run score" }).click();
  await visible(page, "not produced");
  await tab(page, "Explain"); await visible(page, "no overall score could be produced");
});

// ------------------------------------------------------------------ 5. market path (needs key on server)
await step("Market: no key on server -> clear 503 error that says keys live on the server", async () => {
  await reset(); await page.reload();
  await tab(page, "Market");
  await visible(page, "No market data fetched for this symbol yet");
  await page.getByRole("button", { name: "Fetch prices" }).click();
  await visible(page, "PROVIDER_NOT_CONFIGURED"); await visible(page, "never in this dashboard");
  ok(await page.locator("[data-state=error]").first().isVisible(), "error state not shown");
});
await step("Technical/Risk before prices -> actionable error pointing to market data", async () => {
  await tab(page, "Technical"); await page.getByRole("button", { name: "Run technical analysis" }).click();
  await visible(page, "Fetch market data for this symbol first");
  await tab(page, "Risk"); await page.getByRole("button", { name: "Run risk analysis" }).click();
  await visible(page, "Fetch market data for this symbol first");
});
await step("Market with key: prices fetched, chart drawn, rejected bars reported", async () => {
  await control({ marketKeyConfigured: true });
  await tab(page, "Market");
  await page.getByRole("button", { name: "Fetch prices" }).click();
  await visible(page, "non_positive_price ×1");
  await page.getByTestId("line-chart").waitFor({ state: "visible" });
  ok((await page.locator("[data-testid=line-chart] path").count()) === 1, "expected one price line");
  await page.screenshot({ path: `${shots}/market.png`, fullPage: true });
});
await step("Technical: indicators table (computed + not computable) and SMA chart", async () => {
  await tab(page, "Technical"); await visible(page, "No technical analysis yet", 3000).catch(() => {});
  await page.getByRole("button", { name: "Run technical analysis" }).click();
  await visible(page, "Bars needed"); await visible(page, "RSI");
  await page.getByTestId("line-chart").waitFor({ state: "visible" });
  const lines = await page.locator("[data-testid=line-chart] path").count();
  ok(lines >= 3, `expected close + SMA lines, got ${lines}`);
  const legend = await page.locator(".legend").innerText();
  ok(/SMA 20/.test(legend) && /SMA 50/.test(legend), "legend lacks SMA 20/50: " + legend);
});
await step("Suggested action 'Calculate risk' runs risk analysis for the symbol and shows metrics", async () => {
  await tab(page, "Overview");
  const before = count(await logOf(), /^POST \/api\/risk\/AAA$/);
  await chip(page, "Calculate risk");
  await visible(page, "Annualized volatility");
  ok(count(await logOf(), /^POST \/api\/risk\/AAA$/) === before + 1, "risk not run exactly once");
  ok((await page.locator(".tiles .tile").count()) >= 3, "metric tiles missing");
});
await step("Risk: metrics formatted as percentages/plain, warnings shown, benchmark validated", async () => {
  await tab(page, "Risk");
  await page.getByLabel(/Benchmark symbol/).fill("bad sym");
  await visible(page, "Not a valid symbol");
  ok(await page.getByRole("button", { name: "Run risk analysis" }).isDisabled(), "run should be disabled for bad benchmark");
  await page.getByLabel(/Benchmark symbol/).fill("spy");
  await page.getByRole("button", { name: "Run risk analysis" }).click();
  await visible(page, "Annualized volatility");
  const vol = F.risk_metrics.find((m) => m.key === "annualized_volatility").value;
  await visible(page, `${(vol * 100).toFixed(2)}%`);
  ok((await mock.state.log.filter((l) => l.includes("benchmark=SPY")).length) === 1, "benchmark param not sent upper-cased");
});
await step("Sentiment: fetching news without a server key -> 503 hint", async () => {
  await tab(page, "Sentiment");
  await page.getByRole("button", { name: "Fetch & score news" }).click();
  await visible(page, "PROVIDER_NOT_CONFIGURED"); await visible(page, "never in this dashboard");
});
await step("Invalid symbol: dashboard blocks the request instead of calling the API", async () => {
  const header = page.getByLabel("Symbol", { exact: true });
  const before = (await (await fetch(`${BASE}/__log`)).json()).length;
  await header.fill("A B");
  await tab(page, "Market"); await visible(page, "Enter a valid symbol");
  await tab(page, "Score"); await visible(page, "Enter a valid symbol");
  const after = (await (await fetch(`${BASE}/__log`)).json()).filter((l, i) => i >= before && /A%20B|A B/.test(l));
  ok(after.length === 0, "invalid symbol reached the API: " + after.join(","));
  const beforeRisk = count(await logOf(), /POST \/api\/risk/);
  await chip(page, "Calculate risk");
  await visible(page, "Type a valid symbol first");
  ok(count(await logOf(), /POST \/api\/risk/) === beforeRisk, "risk ran with an invalid symbol");
  await header.fill("AAA");
});

// ------------------------------------------------------------------ 6. PDF + unsupported files + failed score
await step("PDF: upload, wrong-tab guidance, extraction with pages, tables and OCR warning", async () => {
  await tab(page, "Files");
  await page.locator("input[type=file]").setInputFiles({ name: "annual.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 demo") });
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  await visible(page, "Uploaded “annual.pdf”");
  await tab(page, "Process"); await visible(page, "is a PDF file, but processing needs XLSX or CSV");
  await tab(page, "PDF"); await visible(page, "has not been extracted yet");
  await page.getByRole("button", { name: "Run extraction" }).click();
  await visible(page, "Page 1"); await visible(page, "Page 2"); await visible(page, "OCR is not performed");
  await page.getByText("Table 1: 2 rows × 2 columns").click(); await visible(page, "1300");
});
await step("Upload of an unsupported type shows the server's error code and message", async () => {
  await tab(page, "Files");
  await page.locator("input[type=file]").setInputFiles({ name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("hello") });
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  await visible(page, "UNSUPPORTED_FILE_TYPE"); await visible(page, "Only .xlsx, .csv and .pdf");
});
await step("Failed score run is shown as FAILED and explain returns the 409 guidance", async () => {
  await control({ failScore: true });
  await tab(page, "Score"); await page.getByRole("button", { name: "Run score" }).click();
  await visible(page, "SCORING_FAILURE");
  await tab(page, "Explain"); await visible(page, "SCORE_NOT_COMPLETE"); await visible(page, "did not complete");
  await control({ failScore: false });
});
await step("Database down: Home explains what is affected and how to fix it", async () => {
  await control({ dbConnected: false });
  await tab(page, "Overview"); await page.getByRole("button", { name: "Refresh" }).click();
  await visible(page, "not connected"); await visible(page, "SQLite");
  await control({ dbConnected: true });
});

// ------------------------------------------------------------------ 7. no secrets / same-origin only / console clean
await step("Network: every request is same-origin /api, no auth headers, no keys in URLs", async () => {
  const api = requests.filter((r) => r.url.includes("/api/"));
  ok(api.length > 30, "too few API requests recorded: " + api.length);
  for (const r of requests) {
    ok(r.url.startsWith(BASE), "cross-origin request: " + r.url);
    ok(!/key=|token=|secret/i.test(r.url), "secret-like text in URL: " + r.url);
    for (const h of ["authorization", "x-api-key", "x-api-token"]) ok(!(h in r.headers), `${h} header sent to ${r.url}`);
  }
});
await step("New workspace clears the selected file and the session activity", async () => {
  await page.getByRole("button", { name: "New workspace" }).click();
  ok((await page.getByTestId("selected-file").innerText()).includes("none selected"), "file not cleared");
  await visible(page, "Nothing yet. Things you run this session appear here.");
});
await step("Responsive (390px phone): drawer menu works, no sideways scrolling, composer stays compact, disclaimer visible", async () => {
  const mobile = await newPage({ width: 390, height: 800 });
  await mobile.goto(BASE);
  ok(!(await mobile.getByRole("navigation").getByRole("button", { name: "Score" }).isVisible().catch(() => false)), "drawer should start closed");
  for (const name of ["Overview", "Score", "Explain", "Market", "Sentiment", "Files"]) {
    await mobile.getByRole("button", { name: "Open menu" }).click();
    await mobile.getByRole("navigation").getByRole("button", { name }).click();
    await mobile.waitForTimeout(350);
    ok(!(await mobile.getByRole("navigation").getByRole("button", { name: "Score" }).isVisible().catch(() => false)), `${name}: drawer did not close`);
    const [sw, iw] = await mobile.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
    ok(sw <= iw + 1, `${name}: page is ${sw}px wide in a ${iw}px window`);
  }
  const split = await mobile.evaluate(() => [...document.querySelectorAll("td.num, th")].filter((c) => c.scrollWidth > c.clientWidth + 1).length);
  ok(split === 0, "table cells overflow/split on mobile: " + split);
  const composer = await mobile.locator(".composer").boundingBox();
  ok(composer && composer.height < 800 * 0.4, "composer too tall on phone: " + (composer && composer.height));
  ok(await mobile.getByTestId("disclaimer").first().isVisible(), "disclaimer hidden on phone");
  await mobile.getByRole("button", { name: "Open menu" }).click();
  await mobile.screenshot({ path: `${shots}/mobile-drawer.png` });
  await mobile.getByRole("button", { name: "Close menu" }).click();
  await mobile.getByRole("navigation").getByRole("button", { name: "Overview" }).waitFor({ state: "hidden" });
  await mobile.screenshot({ path: `${shots}/mobile.png`, fullPage: true });
});
await step("Network failure: backend stopped -> 'Cannot reach the backend' with a fix hint", async () => {
  await tab(page, "Overview");
  await mock.close();
  await page.getByRole("button", { name: "Refresh" }).click();
  await visible(page, "Cannot reach the backend"); await visible(page, "port 8000");
});
await step("Browser console: no errors or React warnings during the whole run", async () => {
  const real = consoleProblems.filter((m) => !/Failed to load resource/.test(m)); // intentional 4xx/5xx/stopped-server responses
  ok(real.length === 0, "console problems:\n  " + real.slice(0, 6).join("\n  "));
});

await browser.close();
const failed = results.filter((r) => !r[0]);
console.log(`\nE2E: ${results.length - failed.length} passed, ${failed.length} failed of ${results.length}`);
fs.rmSync(dist, { recursive: true, force: true });
process.exit(failed.length ? 1 : 0);
