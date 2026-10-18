/** One metric compared across algorithms: bar = mean, whisker = 95% confidence interval. */
export interface MetricRow { label: string; mean: number; lo: number; hi: number; best: boolean }

const fmt = (n: number) => (Math.abs(n) >= 100 ? n.toFixed(0) : n.toFixed(2));

export default function MetricBars({ rows }: { rows: MetricRow[] }) {
  const max = Math.max(...rows.map((r) => Math.max(r.hi, r.mean)), 1e-9);
  return (
    <div role="list">
      {rows.map((r) => (
        <div className="bar-row" role="listitem" key={r.label}>
          <span>{r.label}</span>
          <div className="bar-track" title={`95% CI ${fmt(r.lo)} to ${fmt(r.hi)}`}>
            <div className={`bar-fill ${r.best ? "best" : ""}`} style={{ width: `${(r.mean / max) * 100}%` }} />
            <div className="bar-ci" style={{ left: `${(r.lo / max) * 100}%`, width: `${((r.hi - r.lo) / max) * 100}%` }} />
          </div>
          <span className="mono" style={{ textAlign: "right" }}>{fmt(r.mean)}</span>
        </div>
      ))}
    </div>
  );
}
