/** Grouped histogram: one bar per series inside each bin. All series share the same bin edges. */
export default function Histogram({ edges, counts, colors, labels, xTitle, format = (n) => n.toFixed(0) }: {
  edges: number[]; counts: Record<string, number[]>; colors: Record<string, string>; labels: Record<string, string>;
  xTitle: string; format?: (n: number) => string;
}) {
  const names = Object.keys(counts);
  const bins = edges.length - 1;
  const W = 720, H = 280, left = 46, right = 12, top = 12, bottom = 54;
  const maxCount = Math.max(1, ...names.flatMap((n) => counts[n]));
  const binW = (W - left - right) / bins;
  const barW = Math.max(2, (binW - 4) / names.length);
  const y = (c: number) => top + (1 - c / maxCount) * (H - top - bottom);

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto" }} role="img" aria-label={`Distribution of ${xTitle}`}>
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <g key={f}><line x1={left} x2={W - right} y1={y(maxCount * f)} y2={y(maxCount * f)} className="map-grid" /><text x={left - 6} y={y(maxCount * f) + 4} textAnchor="end" className="map-tick">{Math.round(maxCount * f)}</text></g>
        ))}
        {Array.from({ length: bins }, (_, b) => (
          <g key={b}>
            {names.map((n, k) => (
              <rect key={n} x={left + b * binW + 2 + k * barW} y={y(counts[n][b])} width={barW - 1} height={H - bottom - y(counts[n][b])} rx="2" fill={colors[n]}>
                <title>{`${labels[n]}: ${counts[n][b]} runs between ${format(edges[b])} and ${format(edges[b + 1])}`}</title>
              </rect>
            ))}
            {b % Math.max(1, Math.ceil(bins / 6)) === 0 && <text x={left + b * binW} y={H - bottom + 16} textAnchor="middle" className="map-tick">{format(edges[b])}</text>}
          </g>
        ))}
        <text x={(left + W - right) / 2} y={H - 8} textAnchor="middle" className="hm-axis">{xTitle}</text>
        <text transform={`translate(12 ${(top + H - bottom) / 2}) rotate(-90)`} textAnchor="middle" className="hm-axis">Runs</text>
      </svg>
      <div className="legend">{names.map((n) => <span key={n}><i style={{ background: colors[n] }} />{labels[n]}</span>)}</div>
    </div>
  );
}
