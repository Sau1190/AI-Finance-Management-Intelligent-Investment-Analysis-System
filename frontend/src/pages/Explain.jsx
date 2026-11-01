import { useEffect } from "react";
import { getExplanation } from "../api/client.js";
import { useIntent } from "../hooks/useIntent.js";
import { useRequest } from "../hooks/useRequest.js";
import { useApp } from "../context.js";
import { AsyncView, Badge, Button, Collapsible, EmptyBox, KV, PageHeader, Panel, ScoreRing, Warnings } from "../components/ui.jsx";
import { fmtDateTime, isValidSymbol } from "../lib/format.js";

// Hide drivers that rounded to 0.0 points: a "most points" list should not show zero-point entries.
// (The API still returns the full top-3; this is display only.)
const meaningful = (items) => items.filter((d) => typeof d.points !== "number" || Math.abs(d.points) >= 0.05);

const Sentences = ({ items }) => (
  <ul>{items.map((s, i) => <li key={i}>{typeof s === "string" ? s : s.sentence}</li>)}</ul>
);

export default function Explain() {
  const { symbol, go } = useApp();
  const req = useRequest();
  const valid = isValidSymbol(symbol);
  const load = () => req.run(() => getExplanation(symbol), { emptyOnNotFound: true });
  useEffect(() => { if (valid) load(); else req.reset(); }, [symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  useIntent("load-explanation", () => { if (valid) load(); });

  return (
    <>
      <PageHeader title="Explain the score" subtitle="What the number is, how it was built and why it came out this way, written from fixed templates using only the stored numbers." />
      {!valid ? <EmptyBox>Enter a valid symbol in the Symbol box at the bottom.</EmptyBox> : null}
      {valid ? (
        <Panel title={`What, how and why for ${symbol}`}
          help="A plain-language explanation of the latest score, written from fixed templates using only the stored numbers (no AI model, nothing invented). It explains how the number was built, not whether it is good or what to do."
          actions={<Button onClick={load} busy={req.status === "loading"}>Refresh</Button>}>
          <AsyncView req={req} empty={<>This symbol has no score yet. <button className="link" onClick={() => go("score")}>Run a score first</button>.</>} onRetry={load}>
            {(e) => (
              <>
                <KV items={[["Score id", e.score_id], ["Method version", e.scoring_version], ["Score created", fmtDateTime(e.score_created_at)]]} />
                <Warnings items={e.warnings} />

                <section className="wwh" data-testid="what">
                  <h3>What the score is</h3>
                  <div className="what-row">{typeof e.what.overall_score === "number" ? <ScoreRing value={e.what.overall_score} size={104} /> : null}<p>{e.what.summary}</p></div>
                  <ul>{e.what.components.map((c) => <li key={c.key}>{c.sentence}</li>)}</ul>
                </section>

                <section className="wwh" data-testid="how">
                  <h3>How it was calculated</h3>
                  <ol>{e.how.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
                  {e.how.components.map((c) => (
                    <Collapsible key={c.key} title={c.sentence}>
                      <Sentences items={c.indicators} />
                    </Collapsible>
                  ))}
                  <p className={e.how.arithmetic_check.matches ? "check-ok" : "check-bad"}>
                    <Badge status={e.how.arithmetic_check.matches ? "COMPLETE" : "FAILED"} /> {e.how.arithmetic_check.sentence}
                  </p>
                </section>

                <section className="wwh" data-testid="why">
                  <h3>Why it came out this way</h3>
                  {meaningful(e.why.largest_contributors).length ? <><h4>Added the most points</h4><Sentences items={meaningful(e.why.largest_contributors)} /></> : null}
                  {meaningful(e.why.largest_point_losses).length ? <><h4>Cost the most points</h4><Sentences items={meaningful(e.why.largest_point_losses)} /></> : null}
                  {e.why.accounting ? <p>{e.why.accounting}</p> : null}
                  {e.why.missing_or_excluded.length ? <><h4>Missing or excluded</h4><Sentences items={e.why.missing_or_excluded} /></> : null}
                  <Collapsible title="Why these indicators are in the method"><Sentences items={e.why.why_these_indicators} /></Collapsible>
                  <h4>Assumptions</h4><Sentences items={e.why.assumptions} />
                  <h4>Limits</h4><Sentences items={e.why.limits} />
                </section>
                <p className="notice">{e.notice}</p>
              </>
            )}
          </AsyncView>
        </Panel>
      ) : null}
    </>
  );
}
