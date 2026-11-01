// Turns the latest saved result of each workflow into one small status tile (pure, testable).
import { fmtNum, fmtRiskValue, isNum, labelize } from "./format.js";

export const TILE_KINDS = [
  { kind: "fundamental", label: "Fundamentals", action: "fundamentals", empty: "Needs a processed CSV or Excel file." },
  { kind: "technical", label: "Technical", action: "technical", empty: "Needs stored prices from market data." },
  { kind: "sentiment", label: "Sentiment", action: "sentiment", empty: "Paste headlines to score them." },
  { kind: "risk", label: "Risk", action: "risk", empty: "Needs stored prices from market data." },
  { kind: "market", label: "Market data", action: "market", empty: "Needs a data-provider key on the server." },
];

export function tileFor(kind, req) {
  const meta = TILE_KINDS.find((t) => t.kind === kind);
  if (!req || req.status === "idle") return { state: "empty", value: "—", note: "Nothing requested yet." };
  if (req.status === "loading") return { state: "loading", value: "Loading…", note: "" };
  if (req.status === "empty") return { state: "empty", value: "Not run yet", note: meta ? meta.empty : "" };
  if (req.status === "error") return { state: "error", value: "Could not load", note: req.error?.message || "" };
  const d = req.data || {};
  if (d.status && d.status !== "COMPLETE") return { state: "failed", value: "Last run failed", note: d.error_message || "" };
  switch (kind) {
    case "fundamental": {
      const ms = (d.worksheets || []).flatMap((w) => w.metrics || []);
      const n = ms.filter((m) => m.status === "COMPUTED").length;
      return { state: "ready", value: `${n} of ${ms.length} ratios`, note: "computed from the selected file" };
    }
    case "technical":
      return { state: "ready", value: `${d.bar_count ?? "—"} bars`, note: d.last_date ? `up to ${d.last_date}` : "" };
    case "sentiment":
      return { state: "ready", value: isNum(d.mean_score) ? fmtNum(d.mean_score, 2) : "no signal", note: `${labelize(d.label)} · ${d.scored_count ?? 0} of ${d.text_count ?? 0} texts` };
    case "risk": {
      const vol = (d.metrics || []).find((m) => m.key === "annualized_volatility");
      return { state: "ready", value: vol ? fmtRiskValue(vol) : "—", note: "annualized volatility (past data)" };
    }
    case "market":
      return { state: "ready", value: `${d.bar_count ?? "—"} bars`, note: d.last_date ? `last bar ${d.last_date}` : "" };
    default:
      return { state: "ready", value: "—", note: "" };
  }
}
