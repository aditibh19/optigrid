"use client";
import { useState } from "react";
import { Card, NumberField, PageHead, Notice, Stat, TextField } from "@/components/ui";
import { useRun } from "@/hooks/useRun";
import { allocateFleet, type FleetCharger, type FleetResult, type FleetVehicle } from "@/services/api";

const mk = (id: number, name: string, soc: number, urgency: number, cap = 60, max = 50): FleetVehicle =>
  ({ vehicle_id: id, name, current_soc_pct: soc, target_soc_pct: 80, battery_capacity_kwh: cap, max_charge_rate_kw: max, urgency, deadline_hours: 2 });

const STATUS_TEXT: Record<string, string> = { charging: "Charging", partial: "Reduced power", waiting: "Waiting", at_target: "At target" };
const STATUS_TONE: Record<string, string> = { charging: "real", partial: "demo", waiting: "predicted", at_target: "" };

export default function FleetPage() {
  const [vehicles, setVehicles] = useState<FleetVehicle[]>([mk(1, "Delivery van 1", 15, 5, 80, 60), mk(2, "Delivery van 2", 30, 4, 80, 60), mk(3, "Pool car A", 45, 2, 40, 50), mk(4, "Pool car B", 20, 3, 60, 50), mk(5, "Manager's car", 60, 1, 60, 50), mk(6, "Shuttle", 10, 5, 100, 100)]);
  const [chargers, setChargers] = useState<FleetCharger[]>([{ charger_id: 1, power_kw: 50 }, { charger_id: 2, power_kw: 22 }]);
  const [grid, setGrid] = useState(80);
  const { data, error, busy, run } = useRun<FleetResult>();

  const upd = (idx: number, patch: Partial<FleetVehicle>) => setVehicles((vs) => vs.map((v, k) => (k === idx ? { ...v, ...patch } : v)));
  const valid = vehicles.every((v) => v.name.trim() && [v.current_soc_pct, v.target_soc_pct, v.battery_capacity_kwh, v.max_charge_rate_kw, v.deadline_hours].every(Number.isFinite))
    && chargers.every((c) => Number.isFinite(c.power_kw)) && Number.isFinite(grid);
  const nextId = () => Math.max(0, ...vehicles.map((v) => v.vehicle_id)) + 1;

  return (
    <>
      <PageHead title="Fleet dashboard">
        Several vehicles, a few chargers and a limited grid connection. The allocator decides who gets how much power, favouring urgent vehicles
        that need the most, and never exceeds a charger&apos;s rating or the grid limit.
      </PageHead>

      <Card title="Vehicles" aside={<button className="btn ghost small" disabled={vehicles.length >= 60} onClick={() => setVehicles((v) => [...v, mk(nextId(), `Vehicle ${nextId()}`, 30, 3)])}>Add vehicle</button>}>
        <div className="table-wrap"><table>
          <thead><tr><th>Name</th><th className="num">Charge now %</th><th className="num">Target %</th><th className="num">Battery kWh</th><th className="num">Max kW</th><th className="num">Hours to ready</th><th className="num">Urgency 1-5</th><th /></tr></thead>
          <tbody>{vehicles.map((v, k) => (
            <tr key={v.vehicle_id}>
              <td style={{ minWidth: 150 }}><TextField label="" value={v.name} onChange={(x) => upd(k, { name: x })} /></td>
              {(["current_soc_pct", "target_soc_pct", "battery_capacity_kwh", "max_charge_rate_kw", "deadline_hours"] as const).map((f) => (
                <td key={f} style={{ minWidth: 92 }}><NumberField label="" value={v[f]} onChange={(x) => upd(k, { [f]: x })} min={0} /></td>
              ))}
              <td style={{ minWidth: 80 }}><NumberField label="" value={v.urgency} onChange={(x) => upd(k, { urgency: Math.max(1, Math.min(5, Math.round(x))) })} min={1} max={5} step={1} /></td>
              <td><button className="btn ghost small" onClick={() => setVehicles((vs) => vs.filter((_, j) => j !== k))} disabled={vehicles.length <= 1} aria-label={`Remove ${v.name}`}>Remove</button></td>
            </tr>))}</tbody>
        </table></div>
      </Card>

      <div className="grid cols-2" style={{ marginTop: 18 }}>
        <Card title="Chargers" aside={<button className="btn ghost small" disabled={chargers.length >= 30} onClick={() => setChargers((c) => [...c, { charger_id: Math.max(0, ...c.map((x) => x.charger_id)) + 1, power_kw: 22 }])}>Add charger</button>}>
          <div className="stack">
            {chargers.map((c, k) => (
              <div className="row" key={c.charger_id} style={{ flexWrap: "nowrap" }}>
                <span style={{ minWidth: 90, color: "var(--text-secondary)" }}>Charger {c.charger_id}</span>
                <NumberField label="" value={c.power_kw} onChange={(x) => setChargers((cs) => cs.map((y, j) => (j === k ? { ...y, power_kw: x } : y)))} min={1} suffix="kW" />
                <button className="btn ghost small" disabled={chargers.length <= 1} onClick={() => setChargers((cs) => cs.filter((_, j) => j !== k))}>Remove</button>
              </div>))}
          </div>
        </Card>
        <Card title="Grid connection">
          <div className="stack">
            <NumberField label="Total power available" value={grid} onChange={setGrid} min={1} suffix="kW" hint="The sum of all charging can never exceed this." />
            <button className="btn" onClick={() => void run(() => allocateFleet({ vehicles, chargers, grid_capacity_kw: grid }))} disabled={busy || !valid}>{busy ? "Allocating" : "Allocate power"}</button>
          </div>
        </Card>
      </div>

      <div className="stack" style={{ marginTop: 22 }}>
        {error && <Notice tone="error">{error}</Notice>}
        {data && (
          <>
            <Card title="Result">
              <div className="grid cols-4" style={{ rowGap: 22 }}>
                <Stat label="Grid in use" value={data.totals.grid_used_kw.toFixed(0)} unit={`of ${data.totals.grid_capacity_kw} kW`} tone={data.totals.grid_utilisation_pct >= 99 ? "warn" : "good"} />
                <Stat label="Vehicles charging" value={data.totals.vehicles_charging} />
                <Stat label="Vehicles waiting" value={data.totals.vehicles_waiting} tone={data.totals.vehicles_waiting ? "warn" : "good"} />
                <Stat label="Urgency-weighted service" value={data.service_score_pct.optimised.toFixed(0)} unit="%" tone="good" />
              </div>
              <p className="prose" style={{ marginTop: 16 }}>
                First come, first served would have delivered {data.service_score_pct.first_come_first_served.toFixed(0)}% on the same vehicles, chargers and grid.
                {data.constraint_violations.length === 0 ? " No charger or grid limit is exceeded." : ""}
              </p>
              {data.constraint_violations.map((c) => <Notice key={c} tone="error">{c}</Notice>)}
            </Card>
            <Card title="Who gets what">
              <div className="table-wrap"><table>
                <thead><tr><th>Vehicle</th><th className="num">Urgency</th><th className="num">Needs</th><th className="num">Wanted</th><th>Allocated</th><th className="num">Charger</th><th>Status</th><th className="num">Ready in</th></tr></thead>
                <tbody>{data.vehicles.map((v) => (
                  <tr key={v.vehicle_id}>
                    <td>{v.name}</td><td className="num">{v.urgency}</td><td className="num">{v.needs_kwh} kWh</td><td className="num">{v.desired_kw} kW</td>
                    <td><div className="score"><div className="score-track"><div className="score-fill" style={{ width: `${v.desired_kw ? Math.min(100, (v.allocated_kw / v.desired_kw) * 100) : 0}%` }} /></div><span className="mono">{v.allocated_kw} kW</span></div></td>
                    <td className="num">{v.charger_id ?? "none"}</td><td><span className={`badge ${STATUS_TONE[v.status]}`} title={v.reason}>{STATUS_TEXT[v.status]}</span></td>
                    <td className="num">{v.minutes_to_target !== null ? `${Math.floor(v.minutes_to_target / 60)} h ${v.minutes_to_target % 60} min` : "n/a"}</td>
                  </tr>))}</tbody>
              </table></div>
            </Card>
            <Card title="Charger loads">
              {data.chargers.map((c) => (
                <div className="bar-row" key={c.charger_id} style={{ gridTemplateColumns: "110px 1fr 150px" }}>
                  <span>Charger {c.charger_id}</span>
                  <div className="bar-track"><div className="bar-fill best" style={{ width: `${(c.allocated_kw / c.power_kw) * 100}%` }} /></div>
                  <span className="mono" style={{ textAlign: "right" }}>{c.allocated_kw} / {c.power_kw} kW ({c.vehicle_ids.length} car{c.vehicle_ids.length === 1 ? "" : "s"})</span>
                </div>))}
              <p className="hint" style={{ marginTop: 10, fontSize: 12, color: "var(--text-muted)" }}>{data.note}</p>
            </Card>
          </>
        )}
      </div>
    </>
  );
}
