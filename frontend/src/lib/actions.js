// The suggested actions in the composer and on the overview.
// Each action maps to an EXISTING backend workflow. `resolveAction` is pure: it says which
// page to open and which workflow (if any) that page should start. Nothing is called here.
//
// Workflows that would spend a provider's request quota (market data, news) are never
// started automatically — they only open their page.

export const COMPOSER_ACTIONS = [
  { id: "analyze-file", label: "Analyze a file", icon: "file" },
  { id: "sentiment", label: "Check sentiment", icon: "bubble" },
  { id: "risk", label: "Calculate risk", icon: "gauge" },
  { id: "score", label: "Score this company", icon: "target" },
  { id: "explain", label: "Explain the score", icon: "book" },
];

export const OVERVIEW_ACTIONS = [
  ...COMPOSER_ACTIONS.slice(0, 1),
  { id: "fundamentals", label: "Run fundamentals", icon: "table" },
  { id: "market", label: "Open market data", icon: "candles" },
  { id: "technical", label: "Run technical analysis", icon: "trend" },
  ...COMPOSER_ACTIONS.slice(1),
];

const isTable = (f) => !!f && (f.file_type === "xlsx" || f.file_type === "csv");
const NEED_SYMBOL = "Type a valid symbol first (1–10 letters, digits, “.” or “-”).";
const NEED_FILE = "Choose or upload a file first, then run this action again.";

export function resolveAction(id, { file = null, symbolOk = false } = {}) {
  switch (id) {
    case "analyze-file":
      if (!file) return { tab: "files", intent: null, note: NEED_FILE };
      if (file.file_type === "pdf") return { tab: "pdf", intent: "run-extraction", note: null };
      return { tab: "process", intent: "run-processing", note: null };
    case "fundamentals":
      if (!isTable(file)) return { tab: file ? "fundamentals" : "files", intent: null, note: file ? null : NEED_FILE };
      return { tab: "fundamentals", intent: "run-fundamentals", note: null };
    case "market":
      return { tab: "market", intent: null, note: symbolOk ? null : NEED_SYMBOL };
    case "technical":
      return symbolOk ? { tab: "technical", intent: "run-technical", note: null } : { tab: "technical", intent: null, note: NEED_SYMBOL };
    case "sentiment":
      return symbolOk ? { tab: "sentiment", intent: "focus-headlines", note: null } : { tab: "sentiment", intent: null, note: NEED_SYMBOL };
    case "risk":
      return symbolOk ? { tab: "risk", intent: "run-risk", note: null } : { tab: "risk", intent: null, note: NEED_SYMBOL };
    case "score":
      return symbolOk ? { tab: "score", intent: "run-score", note: null } : { tab: "score", intent: null, note: NEED_SYMBOL };
    case "explain":
      return symbolOk ? { tab: "explain", intent: "load-explanation", note: null } : { tab: "explain", intent: null, note: NEED_SYMBOL };
    default:
      return { tab: "overview", intent: null, note: null };
  }
}
