// A stand-in for the FastAPI backend, used ONLY by the browser test (run-e2e.mjs).
// Response shapes follow backend/app/schemas/*.py; calculation payloads (sentiment,
// fundamentals, technical, risk, score, explanation) come from fixtures.json, which
// make_fixtures.py produced by running the real backend calculation code.
// It is NOT the real backend: it proves the dashboard handles those shapes, not that
// the live server behaves identically. See docs/DASHBOARD.md.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";

const F = JSON.parse(fs.readFileSync(new URL("./fixtures.json", import.meta.url), "utf8"));
const NOW = "2025-01-10T12:00:00+00:00";
const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css" };

export function startMock({ port, distDir }) {
  const s = { files: [], processed: {}, exported: {}, extracted: {}, fundamentals: {}, market: {}, technical: {}, sentiment: null, risk: null, score: null, scoreKind: null,
              flags: { marketKeyConfigured: false, newsKeyConfigured: false, dbConnected: true, failScore: false, slowMs: 0 }, log: [] };
  const err = (res, status, code, message) => send(res, status, { detail: { code, message } });
  const send = (res, status, body, headers = {}) => { res.writeHead(status, { "Content-Type": "application/json", ...headers }); res.end(JSON.stringify(body)); };
  const body = (req) => new Promise((r) => { const c = []; req.on("data", (d) => c.push(d)); req.on("end", () => r(Buffer.concat(c))); });
  const sheetFor = (file) => ({
    sheet_name: file.original_filename.replace(/\.\w+$/, ""), is_empty: false, header_row_index: 0, header_assumed_default: false, row_count: 3, column_count: 8,
    columns: [["Date", "date", "date"], ["Ticker", "string", "ticker"], ["Revenue", "int", "revenue"], ["Net Income", "int", "net_income"], ["Total Assets", "int", "assets"],
              ["Total Liabilities", "int", "liabilities"], ["Shareholders Equity", "int", "equity"], ["Total Debt", "int", "debt"]]
      .map(([name, inferred_type, canonical_concept]) => ({ name, inferred_type, missing_count: 0, canonical_concept, inconsistent_values: null })),
    duplicate_row_count: 0, normalization_mappings: {}, ambiguous_mappings: [], warnings: [], errors: [], cleaned_data_status: "COMPLETE",
    cleaned_data_storage_key: "exports/x.csv", csv_delimiter: file.file_type === "csv" ? "," : null,
  });

  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, "http://x");
    const p = url.pathname;
    s.log.push(`${req.method} ${p}${url.search}`);
    if (s.flags.slowMs && p.startsWith("/api/") && p !== "/api/health") await new Promise((r) => setTimeout(r, s.flags.slowMs));

    if (p === "/__control") { Object.assign(s.flags, JSON.parse((await body(req)).toString() || "{}")); return send(res, 200, s.flags); }
    if (p === "/__log") return send(res, 200, s.log);
    if (p === "/__reset") { s.files = []; s.processed = {}; s.exported = {}; s.extracted = {}; s.fundamentals = {}; s.market = {}; s.technical = {}; s.sentiment = null; s.risk = null; s.score = null; s.log = [];
      s.flags = { marketKeyConfigured: false, newsKeyConfigured: false, dbConnected: true, failScore: false, slowMs: 0 }; return send(res, 200, {}); }

    if (!p.startsWith("/api/")) { // static dashboard bundle
      const f = path.join(distDir, p === "/" ? "index.html" : p);
      if (fs.existsSync(f) && fs.statSync(f).isFile()) { res.writeHead(200, { "Content-Type": MIME[path.extname(f)] || "application/octet-stream" }); return fs.createReadStream(f).pipe(res); }
      res.writeHead(404); return res.end("not found");
    }
    const parts = p.slice(5).split("/").map(decodeURIComponent);
    const m = req.method;

    if (p === "/api/health") return send(res, 200, { status: "ok", service: "AI Finance Management", phase: 12, environment: "development", disclaimer: "x",
      database: { connected: s.flags.dbConnected, error: s.flags.dbConnected ? null : "Database unavailable" } });

    if (parts[0] === "files" && parts.length === 1) {
      if (m === "GET") return send(res, 200, { items: s.files });
      if (m === "POST") {
        const raw = (await body(req)).toString("latin1");
        const name = (raw.match(/filename="([^"]*)"/) || [])[1];
        if (!name) return err(res, 422, "INVALID_REQUEST", "The request could not be processed.");
        const ext = name.split(".").pop().toLowerCase();
        if (!["csv", "xlsx", "pdf"].includes(ext)) return err(res, 400, "UNSUPPORTED_FILE_TYPE", "Only .xlsx, .csv and .pdf files are accepted.");
        const f = { id: `file-${s.files.length + 1}`, original_filename: name, stored_filename: `s-${s.files.length + 1}.${ext}`, file_type: ext, mime_type: null, size_bytes: raw.length,
                    uploaded_at: NOW, processing_status: "READY", error_message: null, storage_key: `uploads/s-${s.files.length + 1}.${ext}` };
        s.files.push(f); return send(res, 201, f);
      }
    }
    if (parts[0] === "files" && parts.length >= 3) {
      const file = s.files.find((x) => x.id === parts[1]);
      if (!file) return err(res, 404, "FILE_NOT_FOUND", "File not found.");
      const what = parts[2], sub = parts[3];
      const key = file.id;
      if (what === "process") {
        if (m === "POST") { s.processed[key] = { id: "proc-1", file_id: key, status: "COMPLETE", created_at: NOW, error_message: null, worksheets: [sheetFor(file)] }; return send(res, 201, s.processed[key]); }
        return s.processed[key] ? send(res, 200, s.processed[key]) : err(res, 404, "PROCESSING_RESULT_NOT_FOUND", "This file has not been processed yet.");
      }
      if (what === "export") {
        if (sub === "download") {
          if (!s.exported[key]) return err(res, 404, "EXPORT_NOT_FOUND", "No completed export is available for this file.");
          res.writeHead(200, { "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Content-Disposition": `attachment; filename="${s.exported[key].original_filename}"` });
          return res.end(Buffer.from("PK-demo-bytes"));
        }
        if (m === "POST") {
          if (!s.processed[key]) return err(res, 404, "PROCESSING_RESULT_NOT_FOUND", "This file has not been processed yet.");
          s.exported[key] = { id: "exp-1", file_id: key, processing_result_id: "proc-1", status: "COMPLETE", created_at: NOW, error_message: null, storage_key: "exports/e.xlsx",
                              original_filename: file.original_filename.replace(/\.\w+$/, "") + "_report.xlsx", sheet_names: ["Cleaned", "Data Quality"] };
          return send(res, 201, s.exported[key]);
        }
        return s.exported[key] ? send(res, 200, s.exported[key]) : err(res, 404, "EXPORT_NOT_FOUND", "This file has not been exported yet.");
      }
      if (what === "extract") {
        if (file.file_type !== "pdf") return err(res, 400, "UNSUPPORTED_FILE_TYPE", "PDF extraction needs a PDF file.");
        if (m === "POST") {
          s.extracted[key] = { id: "ext-1", file_id: key, status: "COMPLETE", created_at: NOW, error_message: null, page_count: 2, pages: [
            { page_number: 1, char_count: 120, text_preview: "Annual report 2024\nRevenue 1,300", text_storage_key: "extracts/a.txt", table_count: 1, warnings: [],
              tables: [{ table_index: 0, row_count: 2, column_count: 2, preview_rows: [["Year", "Revenue"], ["2024", "1300"]], storage_key: "extracts/t.csv" }] },
            { page_number: 2, char_count: 0, text_preview: "", text_storage_key: null, table_count: 0, tables: [], warnings: ["No text found on this page; OCR is not performed."] }] };
          return send(res, 201, s.extracted[key]);
        }
        return s.extracted[key] ? send(res, 200, s.extracted[key]) : err(res, 404, "EXTRACTION_RESULT_NOT_FOUND", "No extraction has been run for this file yet.");
      }
      if (what === "fundamentals") {
        if (m === "POST") {
          if (!s.processed[key]) return err(res, 404, "PROCESSING_RESULT_NOT_FOUND", "This file has not been processed yet.");
          s.fundamentals[key] = { id: "fund-1", file_id: key, processing_result_id: "proc-1", status: "COMPLETE", created_at: NOW, error_message: null, worksheets: [F.sheet] };
          return send(res, 201, s.fundamentals[key]);
        }
        return s.fundamentals[key] ? send(res, 200, s.fundamentals[key]) : err(res, 404, "FUNDAMENTAL_RESULT_NOT_FOUND", "No fundamental analysis has been run for this file yet.");
      }
    }

    const sym = (parts[1] || "").toUpperCase();
    if (parts[0] === "market-data") {
      if (!/^[A-Z0-9.-]{1,10}$/.test(sym)) return err(res, 400, "INVALID_SYMBOL", "A symbol must be 1-10 characters: letters, digits, '.' or '-'.");
      if (parts[2] === "prices") {
        const snap = s.market[sym]; if (!snap) return err(res, 404, "MARKET_RESULT_NOT_FOUND", "No successful market data for this symbol.");
        const limit = Number(url.searchParams.get("limit") || 100); const bars = F.bars.slice(-limit);
        return send(res, 200, { symbol: sym, snapshot_id: "mkt-1", provider: "alpha_vantage", fetched_at: NOW, total_bars: F.bars.length, returned_bars: bars.length, bars });
      }
      if (m === "POST") {
        if (!s.flags.marketKeyConfigured) return err(res, 503, "PROVIDER_NOT_CONFIGURED", "No market data provider key is configured on the server.");
        s.market[sym] = { id: "mkt-1", symbol: sym, provider: "alpha_vantage", history: url.searchParams.get("history") || "compact", status: "COMPLETE", created_at: NOW, error_code: null, error_message: null,
          bar_count: F.bars.length, first_date: F.bars[0].date, last_date: F.bars.at(-1).date, rejected_bars: { non_positive_price: 1 }, preview_bars: F.bars.slice(-5), bars_storage_key: "market/x.csv" };
        return send(res, 201, s.market[sym]);
      }
      return s.market[sym] ? send(res, 200, s.market[sym]) : err(res, 404, "MARKET_RESULT_NOT_FOUND", "No market data has been fetched for this symbol yet.");
    }
    if (parts[0] === "technical") {
      if (parts[2] === "series") {
        if (!s.technical[sym]) return err(res, 404, "TECHNICAL_SERIES_NOT_FOUND", "No successful technical analysis exists for this symbol yet.");
        const limit = Number(url.searchParams.get("limit") || 100); const rows = F.tech_rows.slice(-limit);
        return send(res, 200, { symbol: sym, result_id: "tech-1", market_snapshot_id: "mkt-1", total_rows: F.tech_rows.length, returned_rows: rows.length, rows });
      }
      if (m === "POST") {
        if (!s.market[sym]) return err(res, 404, "MARKET_RESULT_NOT_FOUND", "No successful market data exists for this symbol. Fetch it first.");
        s.technical[sym] = { id: "tech-1", symbol: sym, market_snapshot_id: "mkt-1", status: "COMPLETE", created_at: NOW, error_code: null, error_message: null, bar_count: F.bars.length,
          first_date: F.bars[0].date, last_date: F.bars.at(-1).date, indicators: F.tech_indicators, preview_rows: F.tech_rows.slice(-5), indicators_storage_key: "analysis/t.csv" };
        return send(res, 201, s.technical[sym]);
      }
      return s.technical[sym] ? send(res, 200, s.technical[sym]) : err(res, 404, "TECHNICAL_RESULT_NOT_FOUND", "No technical analysis has been run for this symbol yet.");
    }
    if (parts[0] === "sentiment") {
      if (m === "POST") {
        const raw = parts[2] === "text" ? JSON.parse((await body(req)).toString()) : null;
        if (parts[2] === "news") {
          if (!s.flags.newsKeyConfigured) return err(res, 503, "PROVIDER_NOT_CONFIGURED", "No news provider key is configured on the server.");
          s.sentiment = { ...F.sentiment, source_type: "NEWS", provider: "newsapi", query: url.searchParams.get("query") }; return send(res, 201, s.sentiment);
        }
        if (!raw || !Array.isArray(raw.texts) || raw.texts.length === 0) return err(res, 422, "INVALID_REQUEST", "The request could not be processed.");
        s.sentiment = { ...F.sentiment, symbol: sym, received_count: raw.texts.length }; return send(res, 201, s.sentiment);
      }
      return s.sentiment ? send(res, 200, s.sentiment) : err(res, 404, "SENTIMENT_RESULT_NOT_FOUND", "No sentiment analysis has been run for this symbol yet.");
    }
    if (parts[0] === "risk") {
      if (m === "POST") {
        if (!s.market[sym]) return err(res, 404, "MARKET_RESULT_NOT_FOUND", "No successful market data exists for this symbol. Fetch it first.");
        s.risk = { id: "risk-1", symbol: sym, benchmark_symbol: url.searchParams.get("benchmark"), market_snapshot_id: "mkt-1", benchmark_snapshot_id: null, status: "COMPLETE", created_at: NOW, error_code: null, error_message: null,
          bar_count: F.bars.length, returns_count: F.risk_returns, first_date: F.bars[0].date, last_date: F.bars.at(-1).date, metrics: F.risk_metrics, warnings: F.risk_warnings };
        return send(res, 201, s.risk);
      }
      return s.risk ? send(res, 200, s.risk) : err(res, 404, "RISK_RESULT_NOT_FOUND", "No risk analysis has been run for this symbol yet.");
    }
    if (p === "/api/scoring-method") return send(res, 200, F.scoring_method);
    if (parts[0] === "scores") {
      if (parts[2] === "explanation") {
        if (!s.score) return err(res, 404, "SCORE_RESULT_NOT_FOUND", "No score has been computed for this symbol yet.");
        if (s.score.status !== "COMPLETE") return err(res, 409, "SCORE_NOT_COMPLETE", "The latest score for this symbol did not complete, so there is nothing to explain. Run the score again.");
        return send(res, 200, s.scoreKind);
      }
      if (m === "POST") {
        const b = JSON.parse((await body(req)).toString() || "{}");
        if (b.weights && Object.values(b.weights).every((w) => w === 0)) return err(res, 400, "INVALID_WEIGHTS", "At least one weight must be above zero.");
        if (s.flags.failScore) { s.score = { ...F.score_default, status: "FAILED", error_code: "SCORING_FAILURE", error_message: "The score could not be computed.", overall: null, components: [] }; return send(res, 201, s.score); }
        const hasFund = b.file_id && s.fundamentals[b.file_id];
        if (hasFund && s.sentiment) { const custom = !!b.weights; s.score = custom ? F.score_custom : F.score_default; s.scoreKind = custom ? F.expl_custom : F.expl_default; }
        else if (s.sentiment) { s.score = F.score_one; s.scoreKind = F.expl_one; }
        else return err(res, 404, "SENTIMENT_RESULT_NOT_FOUND", "No successful inputs exist for this symbol. Run at least one analysis first.");
        return send(res, 201, s.score);
      }
      return s.score ? send(res, 200, s.score) : err(res, 404, "SCORE_RESULT_NOT_FOUND", "No score has been computed for this symbol yet.");
    }
    return err(res, 404, "ROUTE_NOT_FOUND", "No such route.");
  });
  return new Promise((r) => server.listen(port, "127.0.0.1", () => r({ server, state: s, close: () => new Promise((c) => server.close(c)) })));
}
