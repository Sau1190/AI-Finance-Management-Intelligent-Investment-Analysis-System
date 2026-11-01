import { useEffect, useState } from "react";
import { fetchMarket, getMarket, getPrices } from "../api/client.js";
import { useRequest } from "../hooks/useRequest.js";
import { useApp } from "../context.js";
import { AsyncView, Badge, Button, DataTable, EmptyBox, Field, KV, PageHeader, Panel } from "../components/ui.jsx";
import LineChart from "../components/LineChart.jsx";
import { fmtDateTime, fmtNum, isValidSymbol } from "../lib/format.js";

export default function Market() {
  const { symbol } = useApp();
  const snap = useRequest();
  const prices = useRequest();
  const [history, setHistory] = useState("compact");
  const valid = isValidSymbol(symbol);

  const loadAll = () => {
    snap.run(() => getMarket(symbol), { emptyOnNotFound: true });
    prices.run(() => getPrices(symbol, 250), { emptyOnNotFound: true });
  };
  useEffect(() => { if (valid) loadAll(); else { snap.reset(); prices.reset(); } }, [symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  async function fetchNow() {
    const s = await snap.run(() => fetchMarket(symbol, history), { log: { label: `Prices fetched for ${symbol}`, tab: "market" } });
    if (s && s.status === "COMPLETE") prices.run(() => getPrices(symbol, 250), { emptyOnNotFound: true });
  }

  return (
    <>
      <PageHeader title="Market data" subtitle="Daily prices from the provider configured on the server, checked bar by bar before anything is stored." />
      {!valid ? <EmptyBox>Enter a valid symbol (1–10 letters, digits, “.” or “-”) in the Symbol box at the bottom.</EmptyBox> : null}
      {valid ? (
        <Panel title={`Daily prices for ${symbol}`}
          help="Fetches daily prices from the configured provider on the server and validates every bar (bad dates, non-positive prices, high below low and duplicates are rejected and counted — never repaired). Prices are NOT adjusted for splits or dividends. Free keys allow only a few requests per minute and about 25 per day, and every click uses quota."
          actions={<Button onClick={fetchNow} busy={snap.status === "loading"}>Fetch prices</Button>}>
          <div className="row">
            <Field label="History">
              <select value={history} onChange={(e) => setHistory(e.target.value)}>
                <option value="compact">compact (about 100 days)</option>
                <option value="full">full (up to ~20 years; needed for the 200-day average)</option>
              </select>
            </Field>
          </div>
          <AsyncView req={snap} empty="No market data fetched for this symbol yet." onRetry={loadAll}>
            {(s) => (
              <>
                <KV items={[
                  ["Status", <Badge status={s.status} />], ["Provider", s.provider], ["History", s.history], ["Fetched", fmtDateTime(s.created_at)],
                  ["Valid bars", s.bar_count], ["First date", s.first_date], ["Last date", s.last_date],
                  s.error_code ? ["Error code", s.error_code] : null, s.error_message ? ["Problem", s.error_message] : null,
                ]} />
                {Object.keys(s.rejected_bars || {}).length ? (
                  <p className="hint">Rejected bars: {Object.entries(s.rejected_bars).map(([k, v]) => `${k} ×${v}`).join(", ")}</p>
                ) : null}
                {s.status === "FAILED" ? <p className="hint">The last fetch failed; earlier successful data (if any) is still used below.</p> : null}
              </>
            )}
          </AsyncView>
        </Panel>
      ) : null}
      {valid ? (
        <Panel title="Closing prices" help="The most recent stored bars from the latest successful fetch.">
          <AsyncView req={prices} empty="No prices stored yet." idle="Fetch prices to see a chart.">
            {(p) => (
              <>
                <p className="muted">{p.returned_bars} of {p.total_bars} bars · provider {p.provider} · fetched {fmtDateTime(p.fetched_at)}</p>
                <LineChart title={`${p.symbol} closing price`} labels={p.bars.map((b) => b.date)} series={[{ name: "Close", values: p.bars.map((b) => b.close) }]} />
                <DataTable
                  columns={[
                    { key: "date", label: "Date" },
                    ...["open", "high", "low", "close"].map((k) => ({ key: k, label: k, num: true, render: (b) => fmtNum(b[k], 2) })),
                    { key: "volume", label: "Volume", num: true, render: (b) => fmtNum(b.volume, 0) },
                  ]}
                  rows={p.bars.slice(-8).reverse()}
                />
              </>
            )}
          </AsyncView>
        </Panel>
      ) : null}
    </>
  );
}
