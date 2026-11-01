import { useEffect } from "react";
import { getFundamentals, getHealth, getMarket, getRisk, getScore, getSentiment, getTechnical, uploadFile } from "../api/client.js";
import { useRequest } from "../hooks/useRequest.js";
import { useApp } from "../context.js";
import { AsyncView, Button, KV, PageHeader, Panel, ScoreRing, Spinner, ErrorBox, Tile } from "../components/ui.jsx";
import Icon from "../components/Icon.jsx";
import { OVERVIEW_ACTIONS } from "../lib/actions.js";
import { navItem } from "../lib/nav.js";
import { TILE_KINDS, tileFor } from "../lib/overview.js";
import { fmtDateTime, fmtNum, fmtPct, isValidSymbol } from "../lib/format.js";
import { SAMPLE_SYMBOL, makeSampleFile } from "../lib/sample.js";

const ACTION_NAV = { "analyze-file": "process", fundamentals: "fundamentals", market: "market", technical: "technical", sentiment: "sentiment", risk: "risk", score: "score", explain: "explain" };

export default function Overview() {
  const { symbol, file, setFile, setSymbol, go, runAction, record, focusSymbol } = useApp();
  const health = useRequest();
  const score = useRequest();
  const sample = useRequest();
  const reqs = { fundamental: useRequest(), technical: useRequest(), sentiment: useRequest(), risk: useRequest(), market: useRequest() };
  const valid = isValidSymbol(symbol);
  const tableFile = file && ["csv", "xlsx"].includes(file.file_type);

  const loadHealth = () => health.run(getHealth);
  useEffect(() => { loadHealth(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const soft = { emptyOnNotFound: true };
    if (!valid) { score.reset(); Object.values(reqs).forEach((r) => r.reset()); return; }
    score.run(() => getScore(symbol), soft);
    reqs.technical.run(() => getTechnical(symbol), soft);
    reqs.sentiment.run(() => getSentiment(symbol), soft);
    reqs.risk.run(() => getRisk(symbol), soft);
    reqs.market.run(() => getMarket(symbol), soft);
  }, [symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (tableFile) reqs.fundamental.run(() => getFundamentals(file.id), { emptyOnNotFound: true });
    else reqs.fundamental.reset();
  }, [file?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadSample() {
    const created = await sample.run(() => uploadFile(makeSampleFile()), { log: { label: "Uploaded the sample CSV", tab: "files" } });
    if (created) { setFile(created); setSymbol(SAMPLE_SYMBOL); }
  }

  const s = score.status === "success" ? score.data : null;
  const overall = s && s.status === "COMPLETE" && s.overall ? s.overall.score : null;

  return (
    <>
      <PageHeader title={valid ? `Company workspace: ${symbol}` : "Company workspace"}
        subtitle="Run the project’s calculations one step at a time and read exactly what each one produced. Every number comes from the backend; nothing here is generated or guessed.">
        <Button variant="ghost" onClick={focusSymbol}>Change symbol</Button>
      </PageHeader>

      <section className="hero card" aria-label="Latest score">
        <div className="hero-main">
          <h2>Latest score for {valid ? symbol : "this symbol"}</h2>
          <AsyncView req={score} empty={<>No score yet for {symbol}. Start with the sample company or run the components you have, then choose “Score this company”.</>} idle="Enter a valid symbol to see saved results.">
            {(r) => (r.status === "COMPLETE" && r.overall ? (
              <div className="hero-score">
                <ScoreRing value={overall} />
                <div>
                  <p className="big-note">
                    {overall === null ? `No overall score was produced: ${r.overall.reason}`
                      : `${r.overall.contributing_components.length} component(s) covering ${fmtPct(r.overall.weight_coverage, 0)} of the weight.`}
                  </p>
                  <p className="muted">Created {fmtDateTime(r.created_at)}. A summary of how indicator values sit against reference ranges. Not a rating or a forecast.</p>
                  <div className="row tight">
                    <Button onClick={() => go("explain")}>Read the explanation</Button>
                    <Button variant="ghost" onClick={() => go("score")}>Open the score</Button>
                  </div>
                </div>
              </div>
            ) : (
              <p className="hint">The last score run did not complete ({r.error_code || "no code"}). Run it again from the Score page.</p>
            ))}
          </AsyncView>
        </div>
      </section>

      <Panel title="What feeds the score" help="The latest saved result of each workflow for this symbol. A missing component is left out of the score and explained; it is never filled in.">
        <div className="tiles">
          {TILE_KINDS.map((t) => {
            // Fundamentals come from the selected file: with no table file there is nothing to load.
            const req = t.kind === "fundamental" && !tableFile ? { status: "empty" } : reqs[t.kind];
            const v = tileFor(t.kind, req);
            return (
              <Tile key={t.kind} label={t.label} value={v.value} note={v.note} status={v.state}
                action={<button className="link" onClick={() => runAction(t.action)}>{v.state === "ready" ? "Open" : t.kind === "market" ? "Open page" : "Run it"}</button>} />
            );
          })}
        </div>
      </Panel>

      <Panel title="What would you like to do?" help="Each card opens one existing workflow. Actions that call a data provider (market data, news) only open their page, because every fetch uses quota.">
        <div className="cards">
          {OVERVIEW_ACTIONS.map((a) => {
            const n = navItem(ACTION_NAV[a.id] || a.id);
            return (
              <button key={a.id} className="action-card" onClick={() => runAction(a.id)}>
                <span className="action-icon"><Icon name={a.icon} size={20} /></span>
                <span className="action-title">{a.label}</span>
                <span className="action-blurb">{n.blurb}</span>
                {n.needs ? <span className="action-needs">Needs: {n.needs}</span> : null}
              </button>
            );
          })}
        </div>
      </Panel>

      <div className="two-col">
        <Panel title="Try it with sample data" help="Creates a small made-up financial table for company AAA, so the whole path works without API keys.">
          <div className="row"><Button onClick={loadSample} busy={sample.status === "loading"}>Load the sample company</Button></div>
          {sample.status === "loading" ? <Spinner label="Uploading the sample…" /> : null}
          {sample.status === "error" ? <ErrorBox error={sample.error} /> : null}
          {sample.status === "success" ? (
            <div className="state success" data-state="success">
              Sample file uploaded and selected, symbol set to {SAMPLE_SYMBOL}. Next: <button className="link" onClick={() => runAction("analyze-file")}>Analyze a file</button> or{" "}
              <button className="link" onClick={() => go("process")}>open Process &amp; report</button>.
            </div>
          ) : <p className="muted">Then: process the file, run fundamentals, score some sample headlines, score the company, and read the explanation.</p>}
        </Panel>

        <Panel title="Backend status" help="This dashboard is only a window onto the backend. If this shows an error, nothing else will work."
          actions={<Button variant="ghost" onClick={loadHealth} busy={health.status === "loading"}>Refresh</Button>}>
          <AsyncView req={health} onRetry={loadHealth}>
            {(h) => (
              <>
                <KV items={[
                  ["Service", h.service],
                  ["Status", h.status],
                  ["Database", h.database?.connected ? "connected" : `not connected${h.database?.error ? ` (${h.database.error})` : ""}`],
                  ["Environment", h.environment],
                  ["Backend phase", fmtNum(h.phase, 0)],
                ]} />
                {!h.database?.connected ? (
                  <p className="hint">The API runs without a database, but uploads and every saved result need one. See “Database” in docs/DASHBOARD.md (SQLite is the easiest for a demo).</p>
                ) : null}
              </>
            )}
          </AsyncView>
          <p className="muted small">API keys live only in the backend <code>.env</code> file. This dashboard never asks for, stores or sends a key.</p>
        </Panel>
      </div>
    </>
  );
}
