import { forwardRef } from "react";
import { COMPOSER_ACTIONS } from "../lib/actions.js";
import { isValidSymbol } from "../lib/format.js";
import Icon from "./Icon.jsx";

// Chat-inspired input area. It is NOT a chat: the only text box is the company symbol,
// and each chip starts one existing backend workflow (see lib/actions.js).
const Composer = forwardRef(function Composer({ symbolInput, setSymbolInput, onAction, onLookup, onPickFile, note, onDismissNote }, ref) {
  const valid = isValidSymbol(symbolInput);
  return (
    <section className="composer" aria-label="Suggested actions">
      {note ? (
        <div className="composer-note" role="status">
          <span>{note}</span>
          <button className="link" onClick={onDismissNote}>Dismiss</button>
        </div>
      ) : null}
      <div className="chips" role="group" aria-label="Suggested actions">
        {COMPOSER_ACTIONS.map((a) => (
          <button key={a.id} type="button" className="chip" onClick={() => onAction(a.id)}>
            <Icon name={a.icon} size={16} /> {a.label}
          </button>
        ))}
      </div>
      <form className={valid ? "composer-box" : "composer-box invalid"} onSubmit={(e) => { e.preventDefault(); onLookup(); }}>
        <button type="button" className="icon-btn" onClick={onPickFile} aria-label="Choose or upload a file"><Icon name="clip" /></button>
        <input ref={ref} aria-label="Symbol" aria-invalid={!valid} value={symbolInput} maxLength={10} autoComplete="off" spellCheck="false"
          placeholder="Company symbol, e.g. AAA" onChange={(e) => setSymbolInput(e.target.value)} />
        <button type="submit" className="send" aria-label="Show saved results for this symbol" disabled={!valid}><Icon name="send" /></button>
      </form>
      <p className="composer-hint">
        {valid ? "A guided workspace, not a chatbot: each button runs one of the project’s existing calculations on the selected symbol and file. Press Enter to see saved results."
          : "A symbol is 1–10 letters, digits, “.” or “-”. This is a guided workspace, not a chatbot."}
      </p>
    </section>
  );
});
export default Composer;
