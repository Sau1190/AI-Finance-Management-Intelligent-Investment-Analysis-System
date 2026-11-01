import { useEffect, useState } from "react";
import { getScore, getScoringMethod, runScore } from "../api/client.js";
import { useIntent } from "../hooks/useIntent.js";
import { useRequest } from "../hooks/useRequest.js";
import { useApp } from "../context.js";
import { AsyncView, Badge, Button, Collapsible, DataTable, EmptyBox, Field, KV, PageHeader, Panel, ScoreBar, ScoreRing, Warnings } from "../components/ui.jsx";
import { fmtDateTime, fmtNum, fmtPct, isValidSymbol, labelize, parseWeights } from "../lib/format.js";

const KEYS = ["fundamental", "technical", "sentiment", "risk"];

export default function Score() {
  const { symbol, file, go } = useApp();
  const req = useRequest();
  const method = useRequest();
  const [useFile, setUseFile] = useState(true);
  const [sheet, setSheet] = useState("");
  const [raw, setRaw] = useState({ fundamental: "", technical: "", sentiment: "", risk: "" });
  const valid = isValidSymbol(symbol);
  const fileOk = file && ["xlsx", "csv"].includes(file.file_type);
  const { weights, error: weightError } = parseWeights(raw);

  const load = () => req.run(() => getScore(symbol), { emptyOnNotFound: true });
  useEffect(() => { if (valid) load(); else req.reset(); }, [symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  function run() {
    const body = {};
    if (useFile && fileOk) { body.file_id = file.id; if (sheet.trim()) body.sheet_name = sheet.trim(); }
    if (weights) body.weights = weights;
    req.run(() => runScore(symbol, body), { log: { label: `Scored ${symbol}`, tab: "score" } });
  }
  useIntent("run-score", () => { if (valid && !weightError) run(); });

  return (
    <>
      <PageHeader title="Score" subtitle="One explainable 0–100 summary of the components that exist. Missing parts are left out and explained, never filled in." />
      {!valid ? <EmptyBox>Enter a valid symbol in the Symbol box at the bottom.</EmptyBox> : null}
      {valid ? (
        <>
          <Panel title={`Score ${symbol}`}
            help="Combines whatever already exists — fundamentals (from a file), technical, sentiment and risk results — into one 0–100 summary of how indicator values sit against fixed reference ranges. Missing parts are left out and explained, never filled in. The reference ranges are illustrative and unvalidated; this is not a rating, a forecast or advice, and there are no buy/sell/hold labels. It needs at least two components.">
            <label className="check">
              <input type="checkbox" checked={useFile && !!fileOk} disabled={!fileOk} onChange={(e) => setUseFile(e.target.checked)} />
              Use the selected file’s fundamentals {fileOk ? `(“${file.original_filename}” — run Fundamentals first)` : "(select a processed CSV/Excel file in Files)"}
            </label>
            {useFile && fileOk ? (
              <Field label="Worksheet name (only if the file has several analysed sheets)">
                <input value={sheet} onChange={(e) => setSheet(e.target.value)} placeholder="optional" />
              </Field>
            ) : null}
            <Collapsible title="Custom weights (optional — leave blank for equal 25% each)">
              <p className="muted">Enter all four or none; the backend normalises them to sum to 1. Changing weights changes the score by exactly the amounts shown in the explanation.</p>
              <div className="row">
                {KEYS.map((k) => (
                  <Field key={k} label={labelize(k)}>
                    <input type="number" min="0" step="any" value={raw[k]} onChange={(e) => setRaw({ ...raw, [k]: e.target.value })} />
                  </Field>
                ))}
              </div>
              {weightError ? <p className="hint">{weightError}</p> : null}
            </Collapsible>
            <div className="row">
              <Button onClick={run} busy={req.status === "loading"} disabled={!!weightError}>Run score</Button>
              <Button variant="ghost" onClick={() => method.run(getScoringMethod)} busy={method.status === "loading"}>Show the scoring method</Button>
            </div>
            <AsyncView req={method} onRetry={() => method.run(getScoringMethod)}>
              {(m) => (
                <Collapsible title={`Method ${m.scoring_version}: weights, rules and limits`} defaultOpen>
                  <p>{m.notice}</p>
                  <h4>Rules</h4><ul>{m.rules.map((x, i) => <li key={i}>{x}</li>)}</ul>
                  <h4>Limits</h4><ul>{m.limits.map((x, i) => <li key={i}>{x}</li>)}</ul>
                </Collapsible>
              )}
            </AsyncView>
          </Panel>

          <Panel title="Result">
            <AsyncView req={req} empty="No score yet for this symbol. Run one above." idle="Run a score to see the result." onRetry={load}>
              {(r) => (
                <>
                  <KV items={[["Status", <Badge status={r.status} />], ["Run at", fmtDateTime(r.created_at)], ["Weights", r.weights_customised ? "custom" : "equal (default)"], r.error_code ? ["Error code", r.error_code] : null, r.error_message ? ["Problem", r.error_message] : null]} />
                  {r.status === "COMPLETE" && r.overall ? (
                    <>
                      <div className="score-hero">
                        <ScoreRing value={r.overall.score} />
                        <div>
                          <h3>Overall score (0–100)</h3>
                          {r.overall.score === null
                            ? <p><strong>Not produced.</strong> {r.overall.reason}</p>
                            : <p>{r.overall.contributing_components.length} component(s) contributed, covering {fmtPct(r.overall.weight_coverage, 0)} of the weight.</p>}
                          <p className="muted">Higher means the indicator values sit closer to the top of fixed, illustrative reference ranges. It is not a rating or a forecast.</p>
                        </div>
                      </div>
                      <DataTable
                        columns={[
                          { key: "label", label: "Component" },
                          { key: "status", label: "Status", render: (c) => <Badge status={c.status} /> },
                          { key: "score", label: "Score", render: (c) => <ScoreBar value={c.score} label={`${c.label} score`} /> },
                          { key: "weight_effective", label: "Effective weight", num: true, render: (c) => (c.weight_effective === null ? "—" : fmtPct(c.weight_effective, 1)) },
                          { key: "contribution_to_overall", label: "Points added", num: true, render: (c) => fmtNum(c.contribution_to_overall, 1) },
                          { key: "reason", label: "Why unavailable", render: (c) => c.reason || "—" },
                        ]}
                        rows={r.components}
                      />
                      <Warnings items={r.warnings} />
                      <p className="notice">{r.notice}</p>
                      <p><button className="link" onClick={() => go("explain")}>Read the What / How / Why explanation</button></p>
                    </>
                  ) : null}
                </>
              )}
            </AsyncView>
          </Panel>
        </>
      ) : null}
    </>
  );
}
