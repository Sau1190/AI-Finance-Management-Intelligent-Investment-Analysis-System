import { useCallback, useRef, useState } from "react";
import { isNotFound, toApiError } from "../lib/errors.js";
import { useApp } from "../context.js";

// One request's lifecycle: idle -> loading -> success | empty | error.
//  * "empty" means a load-latest call found nothing yet (a 404 NOT_FOUND) — not a failure.
//  * Only the most recent call may update the state (older answers are ignored).
//  * `log: { label, tab }` adds an entry to the sidebar's session activity (user-started runs only).
export function useRequest() {
  const { record } = useApp();
  const [state, setState] = useState({ status: "idle", data: null, error: null });
  const seq = useRef(0);

  const run = useCallback(async (fn, { emptyOnNotFound = false, log } = {}) => {
    const id = ++seq.current;
    setState({ status: "loading", data: null, error: null });
    try {
      const data = await fn();
      if (id === seq.current) setState({ status: "success", data, error: null });
      if (log) record({ label: log.label, tab: log.tab, status: "ok" });
      return data;
    } catch (e) {
      const err = toApiError(e);
      if (id === seq.current) {
        setState({ status: emptyOnNotFound && isNotFound(err) ? "empty" : "error", data: null, error: err });
      }
      if (log) record({ label: log.label, tab: log.tab, status: "error" });
      return undefined;
    }
  }, [record]);

  const reset = useCallback(() => {
    seq.current += 1;
    setState({ status: "idle", data: null, error: null });
  }, []);

  return { ...state, run, reset };
}
