import { ramp } from "./color";

/** Row-major matrix; row 0 is drawn at the BOTTOM so "higher SOC" reads upward. */
export default function Heatmap({ matrix, xLabels, yLabels, min, max, stops, xTitle, yTitle, unit = "", showValues = false, decimals = 0 }: {
  matrix: number[][]; xLabels: (string | number)[]; yLabels: (string | number)[]; min: number; max: number; stops: string[];
  xTitle: string; yTitle: string; unit?: string; showValues?: boolean; decimals?: number;
}) {
  const rows = matrix.length, cols = matrix[0]?.length ?? 0;
  const cw = Math.max(18, Math.min(46, 620 / Math.max(cols, 1)));
  const ch = 17;
  const left = 62, top = 8, bottom = 46;
  const W = left + cw * cols + 12, H = top + ch * rows + bottom;
  const labelEvery = cols > 12 ? Math.ceil(cols / 12) : 1;
  const span = max - min || 1;

  return (
    <div>
      <div className="table-wrap">
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", minWidth: Math.min(W, 520), height: "auto" }} role="img" aria-label={`${yTitle} by ${xTitle}`}>
          {matrix.map((row, r) => row.map((v, c) => {
            const y = top + (rows - 1 - r) * ch;
            return (
              <g key={`${r}-${c}`}>
                <title>{`${yTitle} ${yLabels[r]}, ${xTitle} ${xLabels[c]}: ${v.toFixed(decimals)}${unit}`}</title>
                <rect x={left + c * cw} y={y} width={cw - 1} height={ch - 1} rx="2" fill={ramp((v - min) / span, stops)} />
                {showValues && <text x={left + c * cw + cw / 2} y={y + ch / 2 + 4} textAnchor="middle" className="hm-value">{v.toFixed(decimals)}</text>}
              </g>
            );
          }))}
          {yLabels.map((l, r) => (r % 2 === 0 || rows <= 12) && (
            <text key={`y${r}`} x={left - 8} y={top + (rows - 1 - r) * ch + ch / 2 + 4} textAnchor="end" className="map-tick">{l}</text>
          ))}
          {xLabels.map((l, c) => c % labelEvery === 0 && (
            <text key={`x${c}`} x={left + c * cw + cw / 2} y={top + ch * rows + 16} textAnchor="middle" className="map-tick">{l}</text>
          ))}
          <text x={left + (cw * cols) / 2} y={H - 6} textAnchor="middle" className="hm-axis">{xTitle}</text>
        </svg>
      </div>
      <div className="hm-legend" aria-label="Colour scale">
        <span className="mono">{min.toFixed(decimals)}{unit}</span>
        <span className="hm-bar" style={{ background: `linear-gradient(90deg, ${stops.join(", ")})` }} />
        <span className="mono">{max.toFixed(decimals)}{unit}</span>
        <span style={{ marginLeft: 12, color: "var(--text-muted)" }}>{yTitle} runs up the side</span>
      </div>
    </div>
  );
}
