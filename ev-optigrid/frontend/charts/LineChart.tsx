export interface Series { name: string; color: string; points: { x: number | string; y: number; note?: string }[]; step?: boolean }

const nice = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2));

/** Multi-series line chart. String x-values are treated as evenly spaced categories. */
export default function LineChart({ series, xTitle, yTitle, height = 300, yMin, yMax }: {
  step?: boolean;
  series: Series[]; xTitle: string; yTitle: string; height?: number; yMin?: number; yMax?: number;
}) {
  const W = 720, left = 58, right = 18, top = 16, bottom = 52;
  const first = series[0]?.points ?? [];
  if (first.length === 0) return <div className="empty">No data.</div>;
  const categorical = typeof first[0].x === "string";
  const xs = (p: { x: number | string }, i: number) => (categorical ? i : (p.x as number));
  const allX = series.flatMap((s) => s.points.map(xs));
  const allY = series.flatMap((s) => s.points.map((p) => p.y));
  const x0 = Math.min(...allX), x1 = Math.max(...allX);
  const lo = yMin ?? Math.min(0, ...allY);
  let hi = yMax ?? Math.max(...allY);
  if (hi - lo < 1e-9) hi = lo + 1;
  const px = (v: number) => left + ((v - x0) / (x1 - x0 || 1)) * (W - left - right);
  const py = (v: number) => top + (1 - (v - lo) / (hi - lo)) * (height - top - bottom);
  const yTicks = Array.from({ length: 5 }, (_, i) => lo + ((hi - lo) * i) / 4);
  const xTickIdx = first.map((_, i) => i).filter((i) => i % Math.max(1, Math.ceil(first.length / 8)) === 0);

  const path = (s: Series) => {
    const pts = s.points.map((p, i) => [px(xs(p, i)), py(p.y)] as const);
    if (!s.step) return pts.map(([x, y], i) => `${i ? "L" : "M"}${x},${y}`).join(" ");
    return pts.map(([x, y], i) => (i === 0 ? `M${x},${y}` : `H${x}V${y}`)).join(" ");   // hold each value until the next x
  };

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${height}`} style={{ width: "100%", height: "auto" }} role="img" aria-label={`${yTitle} against ${xTitle}`}>
        {yTicks.map((t) => (
          <g key={t}><line x1={left} x2={W - right} y1={py(t)} y2={py(t)} className="map-grid" /><text x={left - 8} y={py(t) + 4} textAnchor="end" className="map-tick">{nice(t)}</text></g>
        ))}
        {xTickIdx.map((i) => <text key={i} x={px(xs(first[i], i))} y={height - bottom + 18} textAnchor="middle" className="map-tick">{String(first[i].x)}</text>)}
        <text x={(left + W - right) / 2} y={height - 8} textAnchor="middle" className="hm-axis">{xTitle}</text>
        <text transform={`translate(14 ${(top + height - bottom) / 2}) rotate(-90)`} textAnchor="middle" className="hm-axis">{yTitle}</text>
        {series.map((s) => (
          <g key={s.name}>
            <path d={path(s)} fill="none" stroke={s.color} strokeWidth="2.5" strokeLinejoin="round" />
            {s.points.map((p, i) => (
              <circle key={i} cx={px(xs(p, i))} cy={py(p.y)} r="3.5" fill={s.color}><title>{`${s.name}: ${p.note ?? String(p.x)} → ${nice(p.y)}`}</title></circle>
            ))}
          </g>
        ))}
      </svg>
      {series.length > 1 && (
        <div className="legend">{series.map((s) => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}</div>
      )}
    </div>
  );
}
