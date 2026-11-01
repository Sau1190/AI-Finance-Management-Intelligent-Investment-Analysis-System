import { useEffect, useRef, useState } from "react";
import { fetchNews, getSentiment, scoreTexts } from "../api/client.js";
import { useIntent } from "../hooks/useIntent.js";
import { useRequest } from "../hooks/useRequest.js";
import { useApp } from "../context.js";
import { AsyncView, Badge, Button, Collapsible, DistBar, EmptyBox, Field, KV, PageHeader, Panel, Stat } from "../components/ui.jsx";
import { fmtDateTime, fmtNum, isValidSymbol, labelize, parseLines } from "../lib/format.js";
import { SAMPLE_HEADLINES } from "../lib/sample.js";

export default function Sentiment() {
  const { symbol } = useApp();
  const req = useRequest();
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const box = useRef(null);
  const valid = isValidSymbol(symbol);
  const lines = parseLines(text);

  const load = () => req.run(() => getSentiment(symbol), { emptyOnNotFound: true });
  useEffect(() => { if (valid) load(); else req.reset(); }, [symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  useIntent("focus-headlines", () => box.current?.focus());
  const scoreNow = () => req.run(() => scoreTexts(symbol, lines), { log: { label: `Scored ${lines.length} headline(s) for ${symbol}`, tab: "sentiment" } });

  return (
    <>
      <PageHeader title="Sentiment" subtitle="A transparent word-list scorer, not an AI model. Every score can be traced to the exact words behind it." />
      {!valid ? <EmptyBox>Enter a valid symbol in the Symbol box at the bottom.</EmptyBox> : null}
      {valid ? (
        <>
          <Panel title={`Headlines for ${symbol}`}
            help="A transparent word-list scorer (no AI model): each headline's score comes from specific words and phrases, with simple negation handling, and you can see exactly which ones. A text with no known words has no score (it is not counted as neutral). Accuracy against real news has NOT been measured; it cannot read sarcasm or context.">
            <Field label="Headlines — one per line" hint={`${lines.length} headline(s). Up to 100, each up to 2000 characters.`}>
              <textarea ref={box} rows={7} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste headlines here, one per line" />
            </Field>
            <div className="row">
              <Button variant="ghost" onClick={() => setText(SAMPLE_HEADLINES)}>Use sample headlines</Button>
              <Button onClick={scoreNow} disabled={lines.length === 0} busy={req.status === "loading"}>Score these headlines</Button>
            </div>
            <div className="row">
              <Field label="Or fetch news (optional search words; defaults to the symbol)" hint="Needs NEWS_API_KEY on the server. Free news plans may be limited to development use — check the provider's terms.">
                <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. company name" />
              </Field>
              <Button variant="ghost" onClick={() => req.run(() => fetchNews(symbol, query.trim()), { log: { label: `News scored for ${symbol}`, tab: "sentiment" } })} busy={req.status === "loading"}>Fetch & score news</Button>
            </div>
          </Panel>
          <Panel title="Result">
            <AsyncView req={req} empty="No sentiment result for this symbol yet." idle="Score some headlines to see a result." onRetry={load}>
              {(r) => (
                <>
                  <KV items={[["Status", <Badge status={r.status} />], ["Source", r.source_type + (r.provider ? ` (${r.provider})` : "")], ["Run at", fmtDateTime(r.created_at)], ["Word list version", r.lexicon_version], r.error_code ? ["Error code", r.error_code] : null, r.error_message ? ["Problem", r.error_message] : null]} />
                  {r.status === "COMPLETE" ? (
                    <>
                      <div className="stats">
                        <Stat label="Average score (−1 … +1)" value={r.mean_score === null ? "no signal" : fmtNum(r.mean_score, 3)} note={`label: ${labelize(r.label)}`} />
                        <Stat label="Texts with a signal" value={`${r.scored_count} / ${r.text_count}`} note={r.coverage === null ? "" : `coverage ${fmtNum(r.coverage * 100, 0)}%`} />
                        <Stat label="Counts" value={Object.entries(r.counts || {}).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"} note="averages can hide disagreement" />
                      </div>
                      <DistBar title="Texts by label" segments={[
                        { label: "positive", value: r.counts?.positive ?? 0, tone: "a" },
                        { label: "neutral", value: r.counts?.neutral ?? 0, tone: "n" },
                        { label: "negative", value: r.counts?.negative ?? 0, tone: "b" },
                        { label: "no signal", value: r.counts?.no_signal ?? 0, tone: "x" },
                      ]} />
                      <p className="muted">Received {r.received_count}; duplicates removed {r.duplicates_removed}{Object.keys(r.skipped || {}).length ? `; skipped ${Object.entries(r.skipped).map(([k, v]) => `${k} ×${v}`).join(", ")}` : ""}.</p>
                      {r.text_count === 0 ? <p className="hint">No usable texts were found — this is an empty result, not a failure.</p> : null}
                      <Collapsible title={`Each text and the words behind its score (${r.items.length})`}>
                        <ul className="items">
                          {r.items.map((it) => (
                            <li key={it.index}>
                              <div>{it.text}</div>
                              <div className="muted">
                                score {it.score === null ? "none (no known words)" : fmtNum(it.score, 3)} · {labelize(it.label)}
                                {it.source ? ` · ${it.source}` : ""}
                              </div>
                              {it.matches.length ? (
                                <div className="muted">words: {it.matches.map((m) => `${m.term} (${m.contribution > 0 ? "+" : ""}${m.contribution}${m.negated ? ", negated" : ""})`).join(", ")}</div>
                              ) : null}
                            </li>
                          ))}
                        </ul>
                      </Collapsible>
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
