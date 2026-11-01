// Pure geometry for the SVG line chart (no React) so it can be tested.

export function niceExtent(values) {
  const nums = values.filter((v) => typeof v === "number" && Number.isFinite(v));
  if (nums.length === 0) return null;
  let min = Math.min(...nums);
  let max = Math.max(...nums);
  if (min === max) { min -= 1; max += 1; }
  const pad = (max - min) * 0.05;
  return { min: min - pad, max: max + pad };
}

// Returns one SVG path string per series. A missing value (null) breaks the line
// instead of being drawn as zero or interpolated.
export function buildPaths(series, width, height, margin = { top: 10, right: 10, bottom: 24, left: 52 }) {
  const all = series.flatMap((s) => s.values);
  const extent = niceExtent(all);
  if (!extent) return { extent: null, paths: series.map(() => "") };
  const n = Math.max(...series.map((s) => s.values.length), 1);
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;
  const x = (i) => margin.left + (n === 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const y = (v) => margin.top + (1 - (v - extent.min) / (extent.max - extent.min)) * innerH;
  const paths = series.map((s) => {
    let d = "";
    let pen = false;
    s.values.forEach((v, i) => {
      if (typeof v === "number" && Number.isFinite(v)) {
        d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
        pen = true;
      } else {
        pen = false;
      }
    });
    return d;
  });
  return { extent, paths, x, y, margin, innerW, innerH };
}
