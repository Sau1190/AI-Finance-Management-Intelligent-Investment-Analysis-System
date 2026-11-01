import { useEffect, useRef, useState } from "react";
import { listFiles, uploadFile } from "../api/client.js";
import { useRequest } from "../hooks/useRequest.js";
import { useApp } from "../context.js";
import { AsyncView, Badge, Button, DataTable, ErrorBox, PageHeader, Panel, Spinner } from "../components/ui.jsx";
import { fmtBytes, fmtDateTime } from "../lib/format.js";
import { makeSampleFile } from "../lib/sample.js";

export default function Files() {
  const { file, setFile, go } = useApp();
  const list = useRequest();
  const upload = useRequest();
  const input = useRef(null);
  const [picked, setPicked] = useState(null);

  const load = () => list.run(listFiles);
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function doUpload(f) {
    const created = await upload.run(() => uploadFile(f), { log: { label: `Uploaded ${f.name}`, tab: "files" } });
    if (created) {
      setFile(created);
      setPicked(null);
      if (input.current) input.current.value = "";
      load();
    }
  }

  return (
    <>
      <PageHeader title="Files" subtitle="Everything starts here: upload a table or PDF, then choose the file the other pages should work on." />
      <Panel title="Upload a file" help="Accepted: .xlsx, .csv, .pdf. The server checks the real file content (not just the name) and never overwrites an original.">
        <div className="row">
          <input ref={input} type="file" accept=".xlsx,.csv,.pdf" aria-label="Choose a file to upload"
            onChange={(e) => setPicked(e.target.files?.[0] || null)} />
          <Button onClick={() => picked && doUpload(picked)} disabled={!picked} busy={upload.status === "loading"}>Upload</Button>
          <Button variant="ghost" onClick={() => doUpload(makeSampleFile())} busy={upload.status === "loading"}>Create & upload the sample CSV</Button>
        </div>
        <p className="muted">The sample is a tiny made-up financial table for company “AAA” (three years). It is for demonstration only.</p>
        {upload.status === "loading" ? <Spinner label="Uploading…" /> : null}
        {upload.status === "error" ? <ErrorBox error={upload.error} /> : null}
        {upload.status === "success" ? (
          <div className="state success" data-state="success">
            Uploaded “{upload.data.original_filename}” ({fmtBytes(upload.data.size_bytes)}, {upload.data.file_type.toUpperCase()}) and selected it.{" "}
            <button className="link" onClick={() => go(upload.data.file_type === "pdf" ? "pdf" : "process")}>Continue</button>
          </div>
        ) : null}
      </Panel>

      <Panel title="Your files" help="Pick the file the other tabs should work on."
        actions={<Button onClick={load} busy={list.status === "loading"}>Refresh</Button>}>
        <AsyncView req={list} onRetry={load} empty="No files yet.">
          {(data) =>
            data.items.length === 0 ? (
              <p className="muted" data-state="empty">No files uploaded yet — upload one above.</p>
            ) : (
              <DataTable
                columns={[
                  { key: "original_filename", label: "File" },
                  { key: "file_type", label: "Type", render: (r) => r.file_type.toUpperCase() },
                  { key: "size_bytes", label: "Size", num: true, render: (r) => fmtBytes(r.size_bytes) },
                  { key: "uploaded_at", label: "Uploaded", render: (r) => fmtDateTime(r.uploaded_at) },
                  { key: "processing_status", label: "Status", render: (r) => <Badge status={r.processing_status} /> },
                  { key: "use", label: "", render: (r) => (
                    file?.id === r.id ? <strong>Selected</strong> : <button className="btn small" onClick={() => setFile(r)}>Use this file</button>
                  ) },
                ]}
                rows={data.items}
              />
            )
          }
        </AsyncView>
      </Panel>
    </>
  );
}
