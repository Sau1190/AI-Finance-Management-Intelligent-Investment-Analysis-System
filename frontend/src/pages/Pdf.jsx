import { useEffect } from "react";
import { getExtraction, runExtraction } from "../api/client.js";
import { useIntent } from "../hooks/useIntent.js";
import { useRequest } from "../hooks/useRequest.js";
import { useApp } from "../context.js";
import { AsyncView, Badge, Button, Collapsible, DataTable, KV, NeedFile, PageHeader, Panel, Warnings } from "../components/ui.jsx";
import { fmtDateTime, fmtNum } from "../lib/format.js";

export default function Pdf() {
  const { file, go } = useApp();
  const req = useRequest();
  const ok = file && file.file_type === "pdf";
  const load = () => req.run(() => getExtraction(file.id), { emptyOnNotFound: true });

  useEffect(() => { if (ok) load(); else req.reset(); }, [file?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = () => req.run(() => runExtraction(file.id), { log: { label: `Extracted ${file.original_filename}`, tab: "pdf" } });
  useIntent("run-extraction", () => { if (ok) start(); });

  return (
    <>
      <PageHeader title="PDF extraction" subtitle="Read the text and tables of each page exactly as written. No interpretation, no OCR." />
      <NeedFile file={file} types={["pdf"]} go={go} what="PDF extraction" />
      {ok ? (
        <Panel title={`Extract “${file.original_filename}”`}
          help="Reads the text of each page and detects tables, exactly as written. It does not interpret numbers and does not do OCR, so scanned (image-only) pages give no text. Password-protected or damaged PDFs fail with a clear message."
          actions={<Button onClick={start} busy={req.status === "loading"}>Run extraction</Button>}>
          <AsyncView req={req} empty="This PDF has not been extracted yet. Click “Run extraction”." onRetry={load}>
            {(r) => (
              <>
                <KV items={[["Status", <Badge status={r.status} />], ["Run at", fmtDateTime(r.created_at)], ["Pages", fmtNum(r.page_count, 0)], ["Problem", r.error_message]]} />
                {r.pages.map((p) => (
                  <div className="sheet" key={p.page_number}>
                    <h3>Page {p.page_number} — {fmtNum(p.char_count, 0)} characters, {p.table_count} table(s)</h3>
                    <Warnings items={p.warnings} />
                    {p.text_preview ? <pre className="preview">{p.text_preview}</pre> : <p className="muted">No text on this page.</p>}
                    {p.tables.map((t) => (
                      <Collapsible key={t.table_index} title={`Table ${t.table_index + 1}: ${t.row_count} rows × ${t.column_count} columns (preview)`}>
                        <DataTable
                          columns={(t.preview_rows[0] || []).map((_, ci) => ({ key: String(ci), label: `Col ${ci + 1}`, render: (row) => row[ci] ?? "" }))}
                          rows={t.preview_rows}
                        />
                      </Collapsible>
                    ))}
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
