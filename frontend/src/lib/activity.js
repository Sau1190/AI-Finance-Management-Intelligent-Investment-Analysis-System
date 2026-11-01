// "Recent activity" list: what the user ran in THIS browser session (kept in memory only,
// never saved to the browser or the server). Pure helpers so they can be unit-tested.
export const MAX_ACTIVITY = 10;

let counter = 0;
export function addActivity(list, entry, now = new Date()) {
  const item = { id: `a${++counter}`, at: now.toISOString(), status: "ok", ...entry };
  const [head, ...rest] = list;
  // Repeating the same action just refreshes the newest entry instead of flooding the list.
  const base = head && head.label === item.label && head.status === item.status ? rest : list;
  return [item, ...base].slice(0, MAX_ACTIVITY);
}

export function timeAgo(iso, now = new Date()) {
  const s = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 1000));
  if (Number.isNaN(s)) return "";
  if (s < 10) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  return h < 24 ? `${h} h ago` : `${Math.round(h / 24)} d ago`;
}
