import { describeError } from "../lib/errors.js";
import { DISCLAIMER } from "../lib/sample.js";
import { fmtNum, isNum } from "../lib/format.js";

export function Disclaimer({ compact = false }) {
  return (
    <div className={compact ? "disclaimer compact" : "disclaimer"} role="note" data-testid="disclaimer">
      <strong>Educational use only.</strong>{" "}
      {compact ? DISCLAIMER : (<><span className="disc-full">{DISCLAIMER}</span><span className="disc-short">Not investment advice.</span></>)}
    </div>
  );
}

export function Panel({ title, help, children, actions }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>{title}</h2>
        {actions ? <div className="panel-actions">{actions}</div> : null}
      </div>
      {help ? <p className="help">{help}</p> : null}
      {children}
    </section>
  );
}

export function Spinner({ label = "Loading…" }) {
  return (
    <div className="state loading" role="status" aria-live="polite" data-state="loading">
      <span className="spinner" aria-hidden="true" /> {label}
    </div>
  );
}

export function ErrorBox({ error, onRetry }) {
  const d = describeError(error);
  return (
    <div className="state error" role="alert" data-state="error">
      <strong>{d.title}.</strong> {d.message}
      {d.code ? <div className="code">Code: {d.code}</div> : null}
      {d.hint ? <div className="hint">{d.hint}</div> : null}
      {onRetry ? <button className="btn small" onClick={onRetry}>Try again</button> : null}
    </div>
  );
}

export function EmptyBox({ children }) {
  return (
    <div className="state empty" data-state="empty">
      {children}
    </div>
  );
}

// Renders exactly one of: idle hint, loading, error, empty, or the result.
export function AsyncView({ req, idle, empty, onRetry, children }) {
  if (req.status === "loading") return <Spinner />;
  if (req.status === "error") return <ErrorBox error={req.error} onRetry={onRetry} />;
  if (req.status === "empty") return <EmptyBox>{empty || "Nothing here yet."}</EmptyBox>;
  if (req.status === "success") {
    return <div className="state success" data-state="success">{children(req.data)}</div>;
  }
  return idle ? <div className="state idle" data-state="idle">{idle}</div> : null;
}

const GOOD = new Set(["COMPLETE", "COMPUTED", "ANALYZED", "READY", "AVAILABLE"]);
const WARN = new Set(["FAILED", "NOT_COMPUTABLE", "SKIPPED", "UNAVAILABLE", "MISSING", "PARTIAL"]);
// Colour only means "did the step run", never "good or bad for the investor".
export function Badge({ status }) {
  const tone = GOOD.has(status) ? "ok" : WARN.has(status) ? "warn" : "neutral";
  return <span className={`badge ${tone}`}>{status || "—"}</span>;
}

export function Button({ children, busy, variant = "primary", ...rest }) {
  return (
    <button className={variant === "primary" ? "btn" : `btn ${variant}`} disabled={busy || rest.disabled} {...rest}>
      {busy ? "Working…" : children}
    </button>
  );
}

export function Field({ label, children, hint }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint ? <span className="field-hint">{hint}</span> : null}
    </label>
  );
}

export function KV({ items }) {
  return (
    <dl className="kv">
      {items.filter(Boolean).map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v === null || v === undefined || v === "" ? "—" : v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function DataTable({ columns, rows, empty = "No rows." }) {
  if (!rows || rows.length === 0) return <p className="muted">{empty}</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>{columns.map((c) => <th key={c.key} className={c.num ? "num" : ""}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c.key} className={c.num ? "num" : ""}>
                  {c.render ? c.render(r) : r[c.key] ?? "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Collapsible({ title, children, defaultOpen = false }) {
  return (
    <details className="collapsible" open={defaultOpen || undefined}>
      <summary>{title}</summary>
      <div className="collapsible-body">{children}</div>
    </details>
  );
}

export function Stat({ label, value, note }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {note ? <div className="stat-note">{note}</div> : null}
    </div>
  );
}

// Horizontal 0-100 bar.
export function ScoreBar({ value, label }) {
  const v = isNum(value) ? Math.max(0, Math.min(100, value)) : null;
  return (
    <div className="scorebar" aria-label={label}>
      <div className="scorebar-track">
        {v !== null ? <div className="scorebar-fill" style={{ width: `${v}%` }} /> : null}
      </div>
      <span className="scorebar-num">{v !== null ? fmtNum(value, 1) : "—"}</span>
    </div>
  );
}

export function Warnings({ items }) {
  if (!items || items.length === 0) return null;
  return (
    <ul className="warnings">
      {items.map((w, i) => <li key={i}>⚠ {w}</li>)}
    </ul>
  );
}

// Shown on pages that need a selected file.
export function NeedFile({ file, types, go, what }) {
  if (!file) {
    return (
      <EmptyBox>
        Choose or upload a file first.{" "}
        <button className="link" onClick={() => go("files")}>Go to Files</button>
      </EmptyBox>
    );
  }
  if (types && !types.includes(file.file_type)) {
    return (
      <EmptyBox>
        “{file.original_filename}” is a {file.file_type.toUpperCase()} file, but {what} needs{" "}
        {types.map((t) => t.toUpperCase()).join(" or ")}. Pick another file in{" "}
        <button className="link" onClick={() => go("files")}>Files</button>.
      </EmptyBox>
    );
  }
  return null;
}

// Big 0-100 ring for the overall score. The colour is the same for every value on purpose:
// the score is a description of how indicators sit against reference ranges, not a verdict.
export function ScoreRing({ value, size = 132, label = "Overall score" }) {
  const v = isNum(value) ? Math.max(0, Math.min(100, value)) : null;
  const r = 52, c = 2 * Math.PI * r;
  return (
    <figure className="ring" data-testid="score-ring" style={{ width: size, height: size }}>
      <svg viewBox="0 0 120 120" role="img" aria-label={v === null ? `${label}: not produced` : `${label}: ${fmtNum(v, 1)} out of 100`}>
        <circle cx="60" cy="60" r={r} className="ring-track" />
        {v !== null ? <circle cx="60" cy="60" r={r} className="ring-fill" strokeDasharray={`${(v / 100) * c} ${c}`} transform="rotate(-90 60 60)" /> : null}
      </svg>
      <figcaption>
        <strong>{v === null ? "—" : fmtNum(v, 1)}</strong>
        <span>of 100</span>
      </figcaption>
    </figure>
  );
}

// One stacked bar from { label, value } segments (e.g. positive / neutral / negative counts).
export function DistBar({ segments, title }) {
  const total = segments.reduce((a, s) => a + (isNum(s.value) ? s.value : 0), 0);
  if (!total) return <p className="muted">Nothing to chart.</p>;
  return (
    <div className="dist" role="img" aria-label={`${title}: ${segments.map((s) => `${s.label} ${s.value}`).join(", ")}`}>
      <div className="dist-bar">
        {segments.filter((s) => s.value > 0).map((s, i) => (
          <span key={s.label} className={`seg seg-${s.tone || i}`} style={{ flexGrow: s.value }} title={`${s.label}: ${s.value}`} />
        ))}
      </div>
      <ul className="dist-legend">
        {segments.map((s, i) => <li key={s.label}><i className={`seg-${s.tone || i}`} /> {s.label} <b>{s.value}</b></li>)}
      </ul>
    </div>
  );
}

// A compact status card: label, a main value, a note, and an optional action.
export function Tile({ label, value, note, status, action }) {
  return (
    <div className="tile" data-status={status || "none"}>
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {note ? <div className="tile-note">{note}</div> : null}
      {action ? <div className="tile-action">{action}</div> : null}
    </div>
  );
}

// Heading block at the top of each workspace page.
export function PageHeader({ title, subtitle, children }) {
  return (
    <header className="page-head">
      <div>
        <h1>{title}</h1>
        {subtitle ? <p className="lede">{subtitle}</p> : null}
      </div>
      {children ? <div className="page-head-extra">{children}</div> : null}
    </header>
  );
}
