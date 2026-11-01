import { useEffect } from "react";
import { getFundamentals, runFundamentals } from "../api/client.js";
import { useIntent } from "../hooks/useIntent.js";
import { useRequest } from "../hooks/useRequest.js";
import { useApp } from "../context.js";
import { AsyncView, Badge, Button, Collapsible, DataTable, KV, NeedFile, PageHeader, Panel, Tile, Warnings } from "../components/ui.jsx";
import { fmtDateTime, fmtNum } from "../lib/format.js";

const TYPES = ["xlsx", "csv"];

export default function Fundamentals() {
  const { file, go } = useApp();
  const req = useRequest();
  const ok = file && TYPES.includes(file.file_type);
  const load = () => req.run(() => getFundamentals(file.id), { emptyOnNotFound: true });
  useEffect(() => { if (ok) load(); else req.reset(); }, [file?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = () => req.run(() => runFundamentals(file.id), { log: { label: `Fundamentals for ${file.original_filename}`, tab: "fundamentals" } });
  useIntent("run-fundamentals", () => { if (ok) start(); });

  return (
    <>
      <PageHeader title="Fundamentals" subtitle="Financial ratios computed row by row from your processed file, with the formula and the reason whenever one is skipped." />
      <NeedFile file={file} types={TYPES} go={go} what="fundamental analysis" />
      {ok ? (
        <Panel title={`Fundamental ratios for “${file.original_filename}”`}
          help="Computes ratios (margins, return on assets/equity, debt and liabilities ratios, P/E, growth) row by row from the processed file. A ratio is only computed when its inputs exist and the denominator is above zero; otherwise it says why it was skipped. Nothing is called good or bad here."
          actions={<Button onClick={start} busy={req.status === "loading"}>Run fundamentals</Button>}>
          <AsyncView req={req} empty="No fundamental analysis yet. Process the file first (Process & report in the sidebar), then click “Run fundamentals”." onRetry={load}>
            {(r) => (
              <>
                <KV items={[["Status", <Badge status={r.status} />], ["Run at", fmtDateTime(r.created_at)], ["Problem", r.error_message]]} />
                {r.worksheets.map((ws) => (
                  <div className="sheet" key={ws.sheet_name}>
                    <h3>Sheet: {ws.sheet_name} <Badge status={ws.status} /></h3>
                    {ws.status === "SKIPPED" ? <p className="muted">Skipped: {ws.reason}</p> : (
                      <>
                        <KV items={[["Rows", ws.row_count], ["Company/ticker column", ws.entity_column], ["Date column", ws.date_column], ["Recognised concepts", ws.recognized_concepts.join(", ")]]} />
                        <div className="tiles">
                          {ws.metrics.filter((m) => m.status === "COMPUTED").slice(0, 4).map((m) => (
                            <Tile key={m.key || m.label} label={m.label} value={fmtNum(m.mean, 4)} note={`mean of ${m.computed_count} row(s)`} status="ready" />
                          ))}
                        </div>
                        <DataTable
                          columns={[
                            { key: "label", label: "Metric" },
                            { key: "status", label: "Status", render: (m) => <Badge status={m.status} /> },
                            { key: "computed_count", label: "Rows computed", num: true },
                            { key: "skipped_count", label: "Skipped", num: true },
                            { key: "min", label: "Min", num: true, render: (m) => fmtNum(m.min, 4) },
                            { key: "mean", label: "Mean", num: true, render: (m) => fmtNum(m.mean, 4) },
                            { key: "max", label: "Max", num: true, render: (m) => fmtNum(m.max, 4) },
                            { key: "formula", label: "Formula" },
                            { key: "reason", label: "Why not computed", render: (m) => m.reason || "—" },
                          ]}
                          rows={ws.metrics}
                        />
                        <Warnings items={ws.warnings} />
                        {ws.preview_rows.length ? (
                          <Collapsible title="Preview of computed rows">
                            <DataTable columns={Object.keys(ws.preview_rows[0]).map((k) => ({ key: k, label: k }))} rows={ws.preview_rows} />
                          </Collapsible>
                        ) : null}
                      </>
                    )}
                  </div>
                ))}
              </>
            )}
          </AsyncView>
        </Panel>
      ) : null}
    </>
  );
}
