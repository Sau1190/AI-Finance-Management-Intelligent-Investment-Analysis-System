import { NAV_GROUPS, navItem } from "../lib/nav.js";
import { timeAgo } from "../lib/activity.js";
import Icon from "./Icon.jsx";

function Mark() {
  return (
    <svg className="mark" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="9" fill="currentColor" opacity="0.16" />
      <path d="M7 22l5-6 4 3 6-9" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="22" cy="10" r="2.2" fill="#d99a1e" />
    </svg>
  );
}

export default function Sidebar({ tab, go, activity, onNew, onClose }) {
  return (
    <aside className="sidebar" id="sidebar" aria-label="Project navigation">
      <div className="side-head">
        <div className="brand"><Mark /><div><strong>Finance workspace</strong><span>Phase 12 dashboard</span></div></div>
        <button className="icon-btn side-close" onClick={onClose} aria-label="Close menu"><Icon name="close" /></button>
      </div>

      <button className="new-btn" onClick={onNew}><Icon name="plus" /> New workspace</button>

      <nav className="side-nav" aria-label="Workflow steps">
        {NAV_GROUPS.map((g, gi) => (
          <div className="side-group" key={gi}>
            {g.title ? <div className="side-title">{g.title}</div> : null}
            {g.items.map((n) => (
              <button key={n.id} className={n.id === tab ? "side-link active" : "side-link"} aria-current={n.id === tab ? "page" : undefined} onClick={() => go(n.id)}>
                <Icon name={n.icon} /> <span>{n.label}</span>
              </button>
            ))}
          </div>
        ))}
      </nav>

      <section className="side-activity" aria-label="Recent activity">
        <div className="side-title">Recent activity</div>
        {activity.length === 0 ? (
          <p className="side-empty">Nothing yet. Things you run this session appear here.</p>
        ) : (
          <ul>
            {activity.map((a) => (
              <li key={a.id}>
                <button className="act" onClick={() => go(a.tab)} title={`Open ${navItem(a.tab).label}`}>
                  <i className={a.status === "ok" ? "dot ok" : "dot err"} aria-label={a.status === "ok" ? "succeeded" : "failed"} />
                  <span className="act-label">{a.label}</span>
                  <span className="act-time">{timeAgo(a.at)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        <p className="side-foot">Kept in memory for this session only.</p>
      </section>
    </aside>
  );
}
