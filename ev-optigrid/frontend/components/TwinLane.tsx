import type { TwinRecord } from "@/services/api";

const LEVEL_COLOR: Record<string, string> = { low: "var(--renewable)", medium: "var(--gold)", high: "var(--urgent)" };

/** One vehicle's charging session at a single time slot: grid, charger, battery, price and solar. */
export default function TwinLane({ title, accent, rec, maxKw, target, safe, capacityKwh }: {
  title: string; accent: string; rec: TwinRecord; maxKw: number; target: number; safe: number; capacityKwh: number;
}) {
  const charging = rec.delivered_kw > 0;
  const soc = rec.soc_after_pct;
  const bx = 232, bw = 130, bh = 46, by = 118;          // battery outline
  const fill = Math.max(0, Math.min(1, soc / 100)) * (bw - 6);
  const flowWidth = 1.5 + 4.5 * Math.min(1, rec.delivered_kw / Math.max(maxKw, 1));

  return (
    <div className="card" style={{ padding: 18 }}>
      <div className="card-head" style={{ marginBottom: 6 }}>
        <h2 style={{ fontSize: 16, color: accent }}>{title}</h2>
        <span className="badge simulated">Simulated</span>
      </div>
      <svg viewBox="0 0 400 210" style={{ width: "100%", height: "auto" }} role="img"
        aria-label={`${title}: ${rec.delivered_kw.toFixed(0)} kW into the battery, now at ${soc.toFixed(0)}%`}>
        {/* solar */}
        <g opacity={0.25 + 0.75 * rec.solar_fraction}>
          <circle cx="36" cy="34" r="12" fill="var(--gold)" />
          {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => (
            <line key={a} x1={36 + 17 * Math.cos((a * Math.PI) / 180)} y1={34 + 17 * Math.sin((a * Math.PI) / 180)}
              x2={36 + 23 * Math.cos((a * Math.PI) / 180)} y2={34 + 23 * Math.sin((a * Math.PI) / 180)} stroke="var(--gold)" strokeWidth="2" strokeLinecap="round" />
          ))}
        </g>
        <text x="36" y="72" textAnchor="middle" className="map-tick">Solar: {rec.solar_level}</text>

        {/* price tag */}
        <g transform="translate(232 14)">
          <rect width="130" height="34" rx="8" fill="var(--ink)" stroke={LEVEL_COLOR[rec.price_level]} />
          <text x="65" y="22" textAnchor="middle" className="twin-num" style={{ fill: LEVEL_COLOR[rec.price_level] }}>₹{rec.price_inr_per_kwh}/kWh</text>
        </g>
        <text x="297" y="64" textAnchor="middle" className="map-tick">Price: {rec.price_level}</text>

        {/* grid meter */}
        <g transform="translate(14 96)">
          <rect width="26" height="90" rx="6" fill="var(--ink)" stroke="var(--line)" />
          <rect x="3" y={3 + 84 * (1 - rec.grid_load_pct / 100)} width="20" height={84 * (rec.grid_load_pct / 100)} rx="4" fill={LEVEL_COLOR[rec.grid_level]} />
          <text x="13" y="106" textAnchor="middle" className="map-tick">Grid</text>
          <text x="13" y="120" textAnchor="middle" className="map-tick">{rec.grid_load_pct}%</text>
        </g>

        {/* wire grid -> charger */}
        <line x1="40" y1="141" x2="92" y2="141" stroke="var(--line)" strokeWidth="3" />
        {charging && <line x1="40" y1="141" x2="92" y2="141" stroke={accent} strokeWidth={flowWidth} className="flow" />}

        {/* charger */}
        <g transform="translate(92 106)">
          <rect width="66" height="70" rx="10" fill="var(--surface-raised)" stroke={charging ? accent : "var(--line)"} strokeWidth="2" />
          <text x="33" y="30" textAnchor="middle" fontSize="20">⚡</text>
          <text x="33" y="52" textAnchor="middle" className="twin-num">{rec.delivered_kw.toFixed(0)} kW</text>
          <text x="33" y="64" textAnchor="middle" className="map-tick">{charging ? "charging" : "idle"}</text>
        </g>

        {/* wire charger -> battery */}
        <line x1="158" y1="141" x2={bx} y2="141" stroke="var(--line)" strokeWidth="3" />
        {charging && <line x1="158" y1="141" x2={bx} y2="141" stroke={accent} strokeWidth={flowWidth} className="flow" />}

        {/* battery */}
        <g>
          <rect x={bx} y={by} width={bw} height={bh} rx="9" fill="var(--ink)" stroke="var(--line)" strokeWidth="2" />
          <rect x={bx + bw} y={by + 14} width="6" height="18" rx="2" fill="var(--line)" />
          <rect x={bx + 3} y={by + 3} width={fill} height={bh - 6} rx="6" fill={soc < safe ? "var(--urgent)" : accent} />
          <text x={bx + bw / 2} y={by + bh / 2 + 6} textAnchor="middle" className="twin-num" style={{ fill: "var(--text-primary)" }}>{soc.toFixed(0)}%</text>
          <line x1={bx + 3 + (target / 100) * (bw - 6)} x2={bx + 3 + (target / 100) * (bw - 6)} y1={by - 6} y2={by + bh + 6} stroke="var(--signal)" strokeWidth="2" />
          <line x1={bx + 3 + (safe / 100) * (bw - 6)} x2={bx + 3 + (safe / 100) * (bw - 6)} y1={by - 6} y2={by + bh + 6} stroke="var(--gold)" strokeWidth="2" strokeDasharray="3 3" />
          <text x={bx + 3 + (target / 100) * (bw - 6)} y={by - 10} textAnchor="middle" className="map-tick" style={{ fill: "var(--signal)" }}>target</text>
          <text x={bx + 3 + (safe / 100) * (bw - 6)} y={by + bh + 20} textAnchor="middle" className="map-tick" style={{ fill: "var(--gold)" }}>safe</text>
        </g>
        <text x={bx + bw / 2} y="200" textAnchor="middle" className="map-tick">{capacityKwh} kWh battery</text>
      </svg>
      <div className="grid cols-3" style={{ marginTop: 6 }}>
        <div className="stat"><span className="label">Spent so far</span><span className="value" style={{ fontSize: 22 }}>₹{rec.cumulative_cost_inr.toFixed(0)}</span></div>
        <div className="stat"><span className="label">Energy delivered</span><span className="value" style={{ fontSize: 22 }}>{rec.cumulative_energy_kwh.toFixed(1)}<small>kWh</small></span></div>
        <div className="stat"><span className="label">This slot</span><span className="value" style={{ fontSize: 22 }}>₹{rec.slot_cost_inr.toFixed(0)}</span></div>
      </div>
    </div>
  );
}
