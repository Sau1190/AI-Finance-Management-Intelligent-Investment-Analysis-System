import { useCallback, useMemo, useRef, useState } from "react";
import { AppContext } from "./context.js";
import { Disclaimer } from "./components/ui.jsx";
import Sidebar from "./components/Sidebar.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import Composer from "./components/Composer.jsx";
import Icon from "./components/Icon.jsx";
import { cleanSymbol, isValidSymbol } from "./lib/format.js";
import { SAMPLE_SYMBOL } from "./lib/sample.js";
import { resolveAction } from "./lib/actions.js";
import { addActivity } from "./lib/activity.js";
import { navItem } from "./lib/nav.js";
import Overview from "./pages/Overview.jsx";
import Files from "./pages/Files.jsx";
import Process from "./pages/Process.jsx";
import Pdf from "./pages/Pdf.jsx";
import Fundamentals from "./pages/Fundamentals.jsx";
import Market from "./pages/Market.jsx";
import Technical from "./pages/Technical.jsx";
import Sentiment from "./pages/Sentiment.jsx";
import Risk from "./pages/Risk.jsx";
import Score from "./pages/Score.jsx";
import Explain from "./pages/Explain.jsx";

const PAGES = { overview: Overview, files: Files, process: Process, pdf: Pdf, fundamentals: Fundamentals, market: Market,
  technical: Technical, sentiment: Sentiment, risk: Risk, score: Score, explain: Explain };

export default function App() {
  const [tab, setTab] = useState("overview");
  const [file, setFile] = useState(null);
  const [symbolInput, setSymbolInput] = useState(SAMPLE_SYMBOL);
  const [drawer, setDrawer] = useState(false);
  const [activity, setActivity] = useState([]);
  const [note, setNote] = useState(null);
  const [intentNonce, setIntentNonce] = useState(0);
  const intentRef = useRef(null);
  const symbolBox = useRef(null);

  const symbol = cleanSymbol(symbolInput);
  const symbolOk = isValidSymbol(symbolInput);
  const Page = PAGES[tab] || Overview;

  const go = useCallback((id) => { setNote(null); setTab(id); setDrawer(false); window.scrollTo?.(0, 0); }, []);
  const record = useCallback((entry) => setActivity((list) => addActivity(list, entry)), []);
  const claimIntent = useCallback((key) => {
    if (intentRef.current && intentRef.current.key === key) { intentRef.current = null; return true; }
    return false;
  }, []);
  const runAction = useCallback((id) => {
    const r = resolveAction(id, { file, symbolOk });
    setNote(r.note);
    setTab(r.tab);
    setDrawer(false);
    window.scrollTo?.(0, 0);
    intentRef.current = r.intent ? { key: r.intent } : null;
    if (r.intent) setIntentNonce((n) => n + 1);
  }, [file, symbolOk]);
  const newWorkspace = useCallback(() => {
    setFile(null); setSymbolInput(SAMPLE_SYMBOL); setActivity([]); setNote(null); intentRef.current = null; go("overview");
  }, [go]);

  const ctx = useMemo(() => ({
    file, setFile, symbol, setSymbol: setSymbolInput, go, record, intentNonce, claimIntent, runAction,
    focusSymbol: () => symbolBox.current?.focus(),
  }), [file, symbol, go, record, intentNonce, claimIntent, runAction]);

  return (
    <AppContext.Provider value={ctx}>
      <div className={drawer ? "app drawer-open" : "app"}>
        <Sidebar tab={tab} go={go} activity={activity} onNew={newWorkspace} onClose={() => setDrawer(false)} />
        <div className="backdrop" onClick={() => setDrawer(false)} aria-hidden="true" />
        <div className="workspace">
          <div className="sticky-top">
            <div className="sticky-disclaimer"><Disclaimer /></div>
            <div className="topbar">
              <button className="icon-btn menu-btn" onClick={() => setDrawer(true)} aria-label="Open menu" aria-controls="sidebar" aria-expanded={drawer}><Icon name="menu" /></button>
              <div className="crumb">{navItem(tab).label}</div>
              <div className="context">
                <span className={symbolOk ? "pill" : "pill bad"} data-testid="selected-symbol">{symbolOk ? symbol : "No valid symbol"}</span>
                <span className="pill file" data-testid="selected-file">
                  File: {file ? `${file.original_filename} (${file.file_type.toUpperCase()})` : "none selected"}
                </span>
              </div>
            </div>
          </div>
          <main className="main" key={tab}>
            <ErrorBoundary key={tab}>
              <Page />
            </ErrorBoundary>
          </main>
          <footer className="footer"><Disclaimer compact /></footer>
          <Composer ref={symbolBox} symbolInput={symbolInput} setSymbolInput={setSymbolInput} onAction={runAction}
            onLookup={() => go("overview")} onPickFile={() => go("files")} note={note} onDismissNote={() => setNote(null)} />
        </div>
      </div>
    </AppContext.Provider>
  );
}
