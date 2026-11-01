import { buildPaths } from "../lib/chart.js";
import { fmtNum } from "../lib/format.js";

const COLORS = ["#0d7c8f", "#d08a12", "#7a4e9b", "#4c8a3c"];

// Dependency-free SVG line chart. Missing values break the line (never drawn as 0).
export default function LineChart({ labels, series, title, height = 240 }) {
  const width = 760;
  const geo = buildPaths(series, width, height);
  if (!geo.extent || !labels || labels.length === 0) return <p className="muted">No data to chart.</p>;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => geo.extent.min + t * (geo.extent.max - geo.extent.min));
  const xIdx = [0, Math.floor((labels.length - 1) / 2), labels.length - 1];
  return (
    <figure className="chart" data-testid="line-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
        <title>{title}</title>
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={geo.margin.left} x2={width - geo.margin.right} y1={geo.y(t)} y2={geo.y(t)} className="grid" />
            <text x={geo.margin.left - 6} y={geo.y(t) + 4} textAnchor="end" className="axis">{fmtNum(t, 2)}</text>
          </g>
        ))}
        {xIdx.map((i) => (
          <text key={i} x={geo.x(i)} y={height - 6} textAnchor={i === 0 ? "start" : i === labels.length - 1 ? "end" : "middle"} className="axis">
            {labels[i]}
          </text>
        ))}
        {geo.paths.map((d, i) => (d ? <path key={i} d={d} fill="none" stroke={COLORS[i % COLORS.length]} strokeWidth="1.8" /> : null))}
      </svg>
      <figcaption className="legend">
        {series.map((s, i) => (
          <span key={s.name}><i style={{ background: COLORS[i % COLORS.length] }} /> {s.name}</span>
        ))}
      </figcaption>
    </figure>
  );
}
