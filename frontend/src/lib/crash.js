// What the dashboard says (and logs) when a page crashes while rendering.
// Deliberately generic: a render error's text can quote data the page was
// showing, so only the error's TYPE goes to the console and nothing from the
// error is ever put on screen.

export const CRASH_TITLE = "This page ran into a problem";
export const CRASH_MESSAGE =
  "Something went wrong while showing this page. Your uploaded files and saved results are not affected. You can try again, or pick another page from the sidebar.";

export function crashLogLine(error) {
  const type = error && typeof error === "object" && error.name ? String(error.name) : "Error";
  return `Dashboard page crashed while rendering: ${type}`;
}
