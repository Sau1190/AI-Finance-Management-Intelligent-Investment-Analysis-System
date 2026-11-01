import { useEffect, useState } from "react";
import { downloadExport, getExport, getProcessing, runExport, runProcessing, saveBlob } from "../api/client.js";
import { useIntent } from "../hooks/useIntent.js";
import { useRequest } from "../hooks/useRequest.js";
import { useApp } from "../context.js";
import { AsyncView, Badge, Button, Collapsible, DataTable, ErrorBox, KV, NeedFile, PageHeader, Panel, Warnings } from "../components/ui.jsx";
import { fmtDateTime } from "../lib/format.js";

const TYPES = ["xlsx", "csv"];

export default function Process() {
  const { file, go } = useApp();
  const proc = useRequest();
  const exp = useRequest();
  const dl = useRequest();
  const [downloaded, setDownloaded] = useState(false);
  const ok = file && TYPES.includes(file.file_type);

  useEffect(() => {
    setDownloaded(false);
    if (!ok) { proc.reset(); exp.reset(); return; }
    proc.run(() => getProcessing(file.id), { emptyOnNotFound: true });
    exp.run(() => getExport(file.id), { emptyOnNotFound: true });
  }, [file?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useIntent("run-processing", () => { if (ok) proc.run(() => runProcessing(file.id), { log: { label: `Processed ${file.original_filename}`, tab: "process" } }); });

  async function download() {
    const blob = await dl.run(() => downloadExport(file.id));
    if (blob) {
      saveBlob(blob, exp.data?.original_filename || "export.xlsx");
      setDownloaded(true);
    }
  }

  return (
    <>
      <PageHeader title="Process & report" subtitle="Read a table the careful way, see what was found, then download a formatted Excel report." />
      <NeedFile file={file} types={TYPES} go={go} what="processing" />
      {ok ? (
        <>
          <Panel title={`Process “${file.original_filename}”`}
            help="Reads every sheet, finds the header row, infers column types, counts missing values and duplicates, and maps known column names (e.g. “Net Income”) to standard concepts. Nothing is guessed silently; the original file is never changed."
            actions={<Button onClick={() => proc.run(() => runProcessing(file.id), { log: { label: `Processed ${file.original_filename}`, tab: "process" } })} busy={proc.status === "loading"}>Run processing</Button>}>
            <AsyncView req={proc} empty="This file has not been processed yet. Click “Run processing”." onRetry={() => proc.run(() => getProcessing(file.id), { emptyOnNotFound: true })}>
              {(r) => (
                <>
                  <KV items={[["Status", <Badge status={r.status} />], ["Run at", fmtDateTime(r.created_at)], ["Problem", r.error_message]]} />
                  {r.worksheets.map((ws) => (
                    <div className="sheet" key={ws.sheet_name}>
                      <h3>Sheet: {ws.sheet_name} <Badge status={ws.cleaned_data_status} /></h3>
                      {ws.is_empty ? <p className="muted">This sheet is empty.</p> : (
                        <>
                          <KV items={[
                            ["Rows", ws.row_count], ["Columns", ws.column_count],
                            ["Header row", ws.header_row_index === null ? "—" : `${ws.header_row_index + 1}${ws.header_assumed_default ? " (assumed default)" : ""}`],
                            ["Duplicate rows", ws.duplicate_row_count],
                            ws.csv_delimiter ? ["CSV delimiter", JSON.stringify(ws.csv_delimiter)] : null,
                          ]} />
                          <DataTable
                            columns={[
                              { key: "name", label: "Column" },
                              { key: "inferred_type", label: "Detected type" },
                              { key: "missing_count", label: "Missing", num: true },
                              { key: "canonical_concept", label: "Standard concept", render: (c) => c.canonical_concept || "—" },
                            ]}
                            rows={ws.columns}
                          />
                          {ws.ambiguous_mappings.length ? (
                            <Collapsible title="Ambiguous column names (left unrenamed on purpose)" defaultOpen>
                              <ul>{ws.ambiguous_mappings.map((a) => <li key={a.canonical_concept}>{a.canonical_concept}: {a.source_columns.join(", ")}</li>)}</ul>
                            </Collapsible>
                          ) : null}
                        </>
                      )}
                      <Warnings items={ws.warnings} />
                      {ws.errors.length ? <ul className="errors">{ws.errors.map((e, i) => <li key={i}>✖ {e}</li>)}</ul> : null}
                    </div>
                  ))}
                  <p><button className="link" onClick={() => go("fundamentals")}>Continue to Fundamentals</button></p>
                </>
              )}
            </AsyncView>
          </Panel>

          <Panel title="Excel report"
            help="Builds a formatted .xlsx workbook from the latest processing result (cleaned data with real numbers and dates, plus a data-quality summary). It only contains what was actually computed."
            actions={<Button onClick={() => exp.run(() => runExport(file.id), { log: { label: "Excel report generated", tab: "process" } })} busy={exp.status === "loading"} disabled={proc.status !== "success"}>Generate report</Button>}>
            {proc.status !== "success" ? <p className="muted">Run processing first (above).</p> : null}
            <AsyncView req={exp} empty="No report generated yet." onRetry={() => exp.run(() => getExport(file.id), { emptyOnNotFound: true })}>
              {(e) => (
                <>
                  <KV items={[["Status", <Badge status={e.status} />], ["Created", fmtDateTime(e.created_at)], ["File name", e.original_filename], ["Sheets", e.sheet_names.join(", ")], ["Problem", e.error_message]]} />
                  {e.status === "COMPLETE" ? (
                    <div className="row">
                      <Button onClick={download} busy={dl.status === "loading"}>Download .xlsx</Button>
                      {downloaded ? <span className="state success" data-state="success">Download started.</span> : null}
                    </div>
                  ) : null}
                  {dl.status === "error" ? <ErrorBox error={dl.error} /> : null}
                </>
              )}
            </AsyncView>
          </Panel>
        </>
      ) : null}
    </>
  );
}
