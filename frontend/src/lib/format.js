// Small, pure formatting helpers (no React, no network) so they are easy to test.

export const isNum = (v) => typeof v === "number" && Number.isFinite(v);

export function fmtNum(v, digits = 2) {
  if (!isNum(v)) return "—";
  return v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

// 0.1234 -> "12.34%". Input is a fraction, not already a percentage.
export function fmtPct(v, digits = 2) {
  return isNum(v) ? `${(v * 100).toFixed(digits)}%` : "—";
}

export function fmtBytes(n) {
  if (!isNum(n) || n < 0) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function fmtDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toISOString().replace("T", " ").slice(0, 16) + " UTC";
}

// snake_case / lower text -> "Snake case"
export function labelize(s) {
  if (typeof s !== "string" || !s) return "—";
  const t = s.replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

// Same rule as the backend (1-10 chars: letters, digits, '.' or '-').
const SYMBOL_RE = /^[A-Za-z0-9.-]{1,10}$/;
export function isValidSymbol(s) {
  return typeof s === "string" && SYMBOL_RE.test(s.trim());
}
export function cleanSymbol(s) {
  return typeof s === "string" ? s.trim().toUpperCase() : "";
}

// One text per non-empty line.
export function parseLines(text) {
  return String(text || "")
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
}

// Risk metrics are fractions (0.02 = 2%) except beta and correlation.
const PLAIN_RISK_KEYS = new Set(["beta", "correlation"]);
export function fmtRiskValue(metric) {
  if (!metric || !isNum(metric.value)) return "—";
  return PLAIN_RISK_KEYS.has(metric.key) ? fmtNum(metric.value, 3) : fmtPct(metric.value, 2);
}

// Parse the optional weight boxes. Blank = not supplied. Returns
// { weights: object|null, error: string|null }. The backend does the real validation.
export function parseWeights(raw) {
  const out = {};
  for (const [key, text] of Object.entries(raw || {})) {
    const t = String(text ?? "").trim();
    if (t === "") continue;
    const n = Number(t);
    if (!Number.isFinite(n) || n < 0) return { weights: null, error: `Weight for ${key} must be a number, 0 or more.` };
    out[key] = n;
  }
  return { weights: Object.keys(out).length ? out : null, error: null };
}
