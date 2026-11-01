import { useEffect } from "react";
import { getTechnical, getTechnicalSeries, runTechnical } from "../api/client.js";
import { useIntent } from "../hooks/useIntent.js";
import { useRequest } from "../hooks/useRequest.js";
import { useApp } from "../context.js";
import { AsyncView, Badge, Button, DataTable, EmptyBox, KV, PageHeader, Panel } from "../components/ui.jsx";
import LineChart from "../components/LineChart.jsx";
import { fmtDateTime, fmtNum, isValidSymbol } from "../lib/format.js";

const OVERLAY = ["sma_20", "sma_50", "sma_200"];

export default function Technical() {
  const { symbol, go } = useApp();
  const res = useRequest();
  const series = useRequest();
  const valid = isValidSymbol(symbol);

  const loadSeries = () => series.run(() => getTechnicalSeries(symbol, 250), { emptyOnNotFound: true });
  const loadAll = () => { res.run(() => getTechnical(symbol), { emptyOnNotFound: true }); loadSeries(); };
  useEffect(() => { if (valid) loadAll(); else { res.reset(); series.reset(); } }, [symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  async function runNow() {
    const r = await res.run(() => runTechnical(symbol), { log: { label: `Technical analysis for ${symbol}`, tab: "technical" } });
    if (r && r.status === "COMPLETE") loadSeries();
  }

  useIntent("run-technical", () => { if (valid) runNow(); });

  return (
    <>
      <PageHeader title="Technical" subtitle="Textbook price indicators computed from stored prices. No buy or sell signals are produced." />
      {!valid ? <EmptyBox>Enter a valid symbol in the Symbol box at the bottom.</EmptyBox> : null}
      {valid ? (
        <Panel title={`Technical indicators for ${symbol}`}
          help="Textbook indicators (SMA 20/50/200, EMA 12/26, MACD, RSI 14, Bollinger Bands, ATR 14) computed from the stored prices. An indicator without enough history is shown as “not computable” with the reason, never estimated from a shorter window. No buy/sell signals are produced."
          actions={<Button onClick={runNow} busy={res.status === "loading"}>Run technical analysis</Button>}>
          <AsyncView req={res} empty={<>No technical analysis yet. It needs stored prices: <button className="link" onClick={() => go("market")}>fetch market data first</button> (Market data in the sidebar).</>} onRetry={loadAll}>
            {(r) => (
              <>
                <KV items={[["Status", <Badge status={r.status} />], ["Run at", fmtDateTime(r.created_at)], ["Bars used", r.bar_count], ["From", r.first_date], ["To", r.last_date], r.error_code ? ["Error code", r.error_code] : null, r.error_message ? ["Problem", r.error_message] : null]} />
                <DataTable
                  columns={[
                    { key: "label", label: "Indicator" },
                    { key: "status", label: "Status", render: (i) => <Badge status={i.status} /> },
                    { key: "latest", label: "Latest", num: true, render: (i) => fmtNum(i.latest, 3) },
                    { key: "latest_date", label: "As of", render: (i) => i.latest_date || "—" },
                    { key: "min_bars", label: "Bars needed", num: true },
                    { key: "reason", label: "Note", render: (i) => i.reason || i.description },
                  ]}
                  rows={r.indicators}
                />
              </>
            )}
          </AsyncView>
        </Panel>
      ) : null}
      {valid ? (
        <Panel title="Price and moving averages" help="Gaps in a line are where an average has no value yet (warm-up) — they are not zeros.">
          <AsyncView req={series} empty="No indicator series yet." idle="Run technical analysis to see the chart.">
            {(s) => {
              const present = OVERLAY.filter((k) => s.rows.some((r) => typeof r[k] === "number"));
              return (
                <LineChart title={`${s.symbol} close with moving averages`} labels={s.rows.map((r) => r.date)}
                  series={[{ name: "Close", values: s.rows.map((r) => r.close) }, ...present.map((k) => ({ name: k.toUpperCase().replace("_", " "), values: s.rows.map((r) => r[k]) }))]} />
              );
            }}
          </AsyncView>
        </Panel>
      ) : null}
    </>
  );
}
