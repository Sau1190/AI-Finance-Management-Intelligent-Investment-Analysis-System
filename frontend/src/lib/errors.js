// Turn any failure into something a beginner can read and act on.
// The backend always sends { detail: { code, message } } and never includes
// paths, stack traces, or keys; we show exactly that and add a plain hint.

export class ApiError extends Error {
  constructor({ kind, status = 0, code = "", message = "" }) {
    super(message);
    this.name = "ApiError";
    this.kind = kind; // "network" | "timeout" | "http"
    this.status = status;
    this.code = code;
  }
}

export function toApiError(e) {
  if (e instanceof ApiError) return e;
  return new ApiError({ kind: "http", status: 0, code: "UNEXPECTED", message: "Something unexpected went wrong in the dashboard." });
}

// A 404 "…_NOT_FOUND" from a *load latest result* call means "nothing here yet",
// which is an empty state, not an error.
export function isNotFound(err) {
  return err instanceof ApiError && err.status === 404 && /NOT_FOUND/.test(err.code || "");
}

export function describeError(err) {
  const e = toApiError(err);
  if (e.kind === "network") {
    return {
      title: "Cannot reach the backend",
      message: e.message,
      code: "",
      hint: "Start the backend (see Backend status on the Overview page) and check that it is running on port 8000, then try again.",
    };
  }
  if (e.kind === "timeout") {
    return {
      title: "The backend is taking too long",
      message: e.message,
      code: "",
      hint: "Nothing was changed in the dashboard. Check that the backend is still running, then try again.",
    };
  }
  let hint = "";
  if (e.code === "DATABASE_FAILURE") {
    hint = "The database could not be reached or the result could not be saved, so nothing was kept. Check that the database is running (see Backend status on the Overview page), then try again.";
  } else if (e.code === "INTERNAL_ERROR") {
    hint = "The backend hit an unexpected problem. Try again; if it keeps happening, check the backend window or log.";
  } else if (e.status === 503) {
    hint = "This feature needs an API key that is stored on the server (in the backend .env file), never in this dashboard. Add the key, restart the backend, and try again.";
  } else if (e.status === 413 || /TOO_LARGE|SIZE/.test(e.code)) {
    hint = "The file is larger than the backend allows (default 10 MB).";
  } else if (e.status === 404 && /MARKET/.test(e.code)) {
    hint = "Fetch market data for this symbol first (open Market data in the sidebar).";
  } else if (e.status === 404 && /PROCESS/.test(e.code)) {
    hint = "Process the file first (open Process & report in the sidebar).";
  } else if (e.status === 404 && /SENTIMENT/.test(e.code)) {
    hint = "Run sentiment first (Sentiment in the sidebar); scoring can also run without it, using fewer components.";
  } else if (e.status === 409) {
    hint = "The previous run for this item did not complete. Run it again.";
  } else if (e.status === 400 || e.status === 422) {
    hint = "Check the value you entered and try again.";
  }
  return { title: "The request did not succeed", message: e.message, code: e.code, hint };
}
