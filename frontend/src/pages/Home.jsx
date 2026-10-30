import { useEffect, useState } from "react";
import { fetchHealth } from "../api/client.js";

export default function Home() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <main className="page">
      <header>
        <p className="eyebrow">Backend API · Phase 9 risk analysis</p>
        <h1>AI Finance Management</h1>
        <p className="lede">
          Explainable financial analysis and investment decision support.
          This is an educational system, not automated trading, and it does
          not promise investment returns.
        </p>
      </header>

      <section className="card">
        <h2>API health</h2>
        {error && (
          <p className="error">
            Could not reach the backend. Start FastAPI first, then refresh.
            Detail: {error}
          </p>
        )}
        {!error && !health && <p>Checking /api/health…</p>}
        {health && (
          <dl>
            <dt>Status</dt>
            <dd>{health.status}</dd>
            <dt>Phase</dt>
            <dd>{health.phase}</dd>
            <dt>Database</dt>
            <dd>
              {health.database.connected
                ? "connected"
                : `disconnected (${health.database.error || "unknown"})`}
            </dd>
          </dl>
        )}
      </section>
    </main>
  );
}
