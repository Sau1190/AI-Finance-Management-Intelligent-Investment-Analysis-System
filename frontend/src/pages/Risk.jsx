import { useEffect, useState } from "react";
import { getRisk, runRisk } from "../api/client.js";
import { useIntent } from "../hooks/useIntent.js";
import { useRequest } from "../hooks/useRequest.js";
import { useApp } from "../context.js";
import { AsyncView, Badge, Button, DataTable, EmptyBox, Field, KV, PageHeader, Panel, Tile, Warnings } from "../components/ui.jsx";
import { cleanSymbol, fmtDateTime, fmtRiskValue, isValidSymbol } from "../lib/format.js";

export default function Risk() {
  const { symbol, go } = useApp();
  const req = useRequest();
  const [benchmark, setBenchmark] = useState("");
  const valid = isValidSymbol(symbol);
  const bench = cleanSymbol(benchmark);
  const benchOk = bench === "" || isValidSymbol(bench);

  const load = () => req.run(() => getRisk(symbol), { emptyOnNotFound: true });
  useEffect(() => { if (valid) load(); else req.reset(); }, [symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = () => req.run(() => runRisk(symbol, bench), { log: { label: `Risk analysis for ${symbol}`, tab: "risk" } });
  useIntent("run-risk", () => { if (valid && benchOk) start(); });

  return (
    <>
      <PageHeader title="Risk" subtitle="Descriptive statistics of past daily price moves. They describe history; they are not forecasts and carry no risk labels." />
      {!valid ? <EmptyBox>Enter a valid symbol in the Symbol box at the bottom.</EmptyBox> : null}
      {valid ? (
        <Panel title={`Risk metrics for ${symbol}`}
          help="Descriptive statistics of past daily price moves: volatility, worst fall from a peak, best/worst day, historical VaR/CVaR (a 95% VaR of −2% means about 5% of past days were 2% worse or lower), and beta/correlation against a benchmark you have also fetched. These describe history, are not forecasts, and carry no “high/low risk” labels. A stock split in unadjusted prices looks like a crash and is flagged."
          actions={<Button onClick={start} busy={req.status === "loading"} disabled={!benchOk}>Run risk analysis</Button>}>
          <div className="row">
            <Field label="Benchmark symbol (optional, e.g. SPY)" hint={benchOk ? "Fetch the benchmark's prices in Market data first." : "Not a valid symbol."}>
              <input value={benchmark} onChange={(e) => setBenchmark(e.target.value)} placeholder="optional" />
            </Field>
          </div>
          <AsyncView req={req} empty={<>No risk analysis yet. It needs stored prices: <button className="link" onClick={() => go("market")}>fetch market data first</button> (Market data in the sidebar).</>} onRetry={load}>
            {(r) => (
              <>
                <KV items={[["Status", <Badge status={r.status} />], ["Run at", fmtDateTime(r.created_at)], ["Daily returns", r.returns_count], ["From", r.first_date], ["To", r.last_date], r.benchmark_symbol ? ["Benchmark", r.benchmark_symbol] : null, r.error_code ? ["Error code", r.error_code] : null, r.error_message ? ["Problem", r.error_message] : null]} />
                <Warnings items={r.warnings} />
                <div className="tiles">
                  {r.metrics.filter((m) => m.status === "COMPUTED").slice(0, 4).map((m) => (
                    <Tile key={m.key} label={m.label} value={fmtRiskValue(m)} note="past data only" status="ready" />
                  ))}
                </div>
                <DataTable
                  columns={[
                    { key: "label", label: "Metric" },
                    { key: "status", label: "Status", render: (m) => <Badge status={m.status} /> },
                    { key: "value", label: "Value", num: true, render: (m) => fmtRiskValue(m) },
                    { key: "reason", label: "Note", render: (m) => m.reason || m.description },
                  ]}
                  rows={r.metrics}
                />
              </>
            )}
          </AsyncView>
        </Panel>
      ) : null}
    </>
  );
}
