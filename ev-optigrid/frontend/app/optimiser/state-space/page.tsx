"use client";
import { useEffect, useState } from "react";
import { Card, NumberField, PageHead, Notice, Stat, errorMessage } from "@/components/ui";
import { getSocTransition, getStateSpace, type SocTransition, type StateSpace } from "@/services/api";
import { ramp } from "@/charts/color";

function Matrix({ title, levels, m }: { title: string; levels: string[]; m: number[][] }) {
  return (
    <div>
      <h3 style={{ fontSize: 15, marginBottom: 8 }}>{title}</h3>
      <div className="matrix" style={{ gridTemplateColumns: `auto repeat(${levels.length}, 1fr)` }}>
        <span className="head">from / to</span>
        {levels.map((l) => <span key={l} className="head">{l}</span>)}
        {m.map((row, i) => (
          <>
            <span key={`h${i}`} className="head">{levels[i]}</span>
            {row.map((p, j) => <span key={`${i}-${j}`} className="cell" style={{ background: ramp(p, ["#1B1E29", "#453B7A", "#8B7BFA"]) }} title={`P(${levels[i]} to ${levels[j]}) = ${p}`}>{p.toFixed(2)}</span>)}
          </>
        ))}
      </div>
    </div>
  );
}

export default function StateSpacePage() {
  const [space, setSpace] = useState<StateSpace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tr, setTr] = useState({ soc_pct: 30, action_kw: 5, battery_capacity_kwh: 60, slot_minutes: 15 });
  const [trResult, setTrResult] = useState<SocTransition | null>(null);

  useEffect(() => { getStateSpace().then(setSpace).catch((e) => setError(errorMessage(e))); }, []);
  useEffect(() => {
    if (![tr.soc_pct, tr.action_kw, tr.battery_capacity_kwh, tr.slot_minutes].every(Number.isFinite)) return;
    const t = setTimeout(() => { getSocTransition(tr).then(setTrResult).catch(() => setTrResult(null)); }, 250);
    return () => clearTimeout(t);
  }, [tr]);
  const setT = <K extends keyof typeof tr>(k: K, v: number) => setTr((s) => ({ ...s, [k]: v }));

  return (
    <>
      <PageHead title="State space">
        Charging is modelled as a Markov decision process: at every time slot the optimiser sees a state,
        picks a charging power, pays a cost, and the world moves to a new state. This page shows exactly what a state is.
      </PageHead>
      {error && <Notice tone="error">{error}</Notice>}
      {space && (
        <div className="stack" style={{ gap: 22 }}>
          <Card title="Size of the problem">
            <div className="grid cols-4" style={{ rowGap: 22 }}>
              <Stat label="Battery levels" value={space.counts.soc} unit={`steps of ${space.soc_step_pct}%`} />
              <Stat label="Price levels" value={space.counts.price} />
              <Stat label="Grid-load levels" value={space.counts.grid} />
              <Stat label="Solar levels" value={space.counts.solar} />
              <Stat label="States per time slot" value={space.counts.states_per_slot.toLocaleString()} tone="signal" />
              <Stat label="Charging powers" value={space.counts.actions} unit="choices" />
              <Stat label="State-action pairs per slot" value={space.counts.state_action_pairs_per_slot.toLocaleString()} />
              <Stat label="Discount factor" value={space.gamma} />
            </div>
            <p className="prose" style={{ marginTop: 18 }}>
              A state is (battery level, price level, grid load level, solar level). The optimiser evaluates every state-action pair at every
              slot, working backwards from the deadline (value iteration), so the whole problem is solved exactly rather than approximated.
            </p>
          </Card>

          <Card title="What the levels mean">
            <div className="table-wrap"><table>
              <thead><tr><th>Quantity</th><th>Low</th><th>Medium</th><th>High</th><th>Thresholds</th></tr></thead>
              <tbody>
                <tr><td>Electricity price</td>{space.price.values_inr_per_kwh.map((v) => <td key={v} className="num">₹{v}/kWh</td>)}<td className="num">below {space.price.thresholds[0]} / above {space.price.thresholds[1]} ₹/kWh</td></tr>
                <tr><td>Grid load</td>{space.grid.values_load_pct.map((v) => <td key={v} className="num">{v}%</td>)}<td className="num">below {space.grid.thresholds[0]}% / above {space.grid.thresholds[1]}%</td></tr>
                <tr><td>Solar availability</td>{space.solar.values_fraction.map((v, i) => <td key={i} className="num">{space.solar.levels[i]}: {v}</td>)}<td className="num">below {space.solar.thresholds[0]} / above {space.solar.thresholds[1]}</td></tr>
              </tbody>
            </table></div>
            <p className="hint" style={{ marginTop: 10, fontSize: 12, color: "var(--text-muted)" }}>Each level stands for one representative value, which is what the cost function uses.</p>
          </Card>

          <Card title="How the world changes between slots">
            <p className="prose" style={{ marginBottom: 16 }}>
              Price, grid load and solar are uncertain. Each is a Markov chain: the probability of the next level depends only on the current level.
              Rows are the current level and each row sums to 1. Strong diagonals mean conditions tend to persist.
            </p>
            <div className="grid cols-3">
              <Matrix title="Price" levels={space.price.levels} m={space.transition_matrices.price} />
              <Matrix title="Grid load" levels={space.grid.levels} m={space.transition_matrices.grid} />
              <Matrix title="Solar" levels={space.solar.levels} m={space.transition_matrices.solar} />
            </div>
            <p className="prose" style={{ marginTop: 16, fontSize: 13 }}>{space.notes[0]}</p>
          </Card>

          <Card title="How the battery level moves">
            <p className="prose" style={{ marginBottom: 16 }}>
              Battery level is tracked in {space.soc_step_pct}-point buckets, but a slow charger adds less than one bucket per slot. Rounding to the nearest
              bucket would make the gain vanish and the optimiser would conclude that slow charging never helps. Instead the result is split between the two
              neighbouring buckets so that the <em>expected</em> bucket equals the true value. Try a small charger on a big battery:
            </p>
            <div className="grid cols-4" style={{ marginBottom: 18 }}>
              <NumberField label="Battery now" value={tr.soc_pct} onChange={(v) => setT("soc_pct", v)} min={0} max={100} suffix="%" />
              <NumberField label="Charging power" value={tr.action_kw} onChange={(v) => setT("action_kw", v)} min={0} suffix="kW" />
              <NumberField label="Battery size" value={tr.battery_capacity_kwh} onChange={(v) => setT("battery_capacity_kwh", v)} min={1} suffix="kWh" />
              <NumberField label="Slot length" value={tr.slot_minutes} onChange={(v) => setT("slot_minutes", Math.round(v))} min={1} max={120} suffix="min" />
            </div>
            {trResult && (
              <div className="grid cols-2">
                <div className="stack">
                  <Stat label="True battery level after the slot" value={trResult.soc_after_continuous_pct.toFixed(2)} unit="%" tone="signal" />
                  <Stat label="Expected bucket with interpolation" value={trResult.expected_bucket_soc_pct.toFixed(2)} unit="%" tone="good" />
                  <Stat label="Nearest-bucket rounding would give" value={trResult.nearest_bucket_soc_pct.toFixed(0)} unit="%" tone={trResult.nearest_bucket_soc_pct === trResult.start_bucket_soc_pct && trResult.gain_pct > 0 ? "bad" : undefined} />
                  {trResult.nearest_bucket_soc_pct === trResult.start_bucket_soc_pct && trResult.gain_pct > 0 && (
                    <Notice tone="warn">Rounding would leave the battery at {trResult.start_bucket_soc_pct}%, as if this charge never happened.</Notice>
                  )}
                </div>
                <div>
                  <h3 style={{ fontSize: 15, marginBottom: 10 }}>Next-bucket probabilities</h3>
                  {trResult.distribution.map((d) => (
                    <div className="bar-row" key={d.bucket_index} style={{ gridTemplateColumns: "70px 1fr 60px" }}>
                      <span className="mono">{d.bucket_soc_pct}%</span>
                      <div className="bar-track"><div className="bar-fill best" style={{ width: `${d.probability * 100}%` }} /></div>
                      <span className="mono" style={{ textAlign: "right" }}>{(d.probability * 100).toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
