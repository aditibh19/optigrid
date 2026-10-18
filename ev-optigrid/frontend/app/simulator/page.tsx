"use client";
import { useEffect, useState } from "react";
import MetricBars, { type MetricRow } from "@/charts/MetricBars";
import { Card, NumberField, PageHead, Notice, SourceBadge, allFinite, errorMessage } from "@/components/ui";
import { getSimulationLimits, runSimulation, type SimulationLimits, type SimulationParams, type SimulationRun } from "@/services/api";

const humanise = (s: string) => { const t = s.replace(/_/g, " "); return t.charAt(0).toUpperCase() + t.slice(1); };
const higherIsBetter = (metric: string) => /renewable|utili[sz]ation/.test(metric);

export default function SimulatorPage() {
  const [p, setP] = useState<SimulationParams>({
    num_evs: 10, num_chargers: 4, charger_power_kw: 50, grid_capacity_kw: 150, horizon_slots: 24, n_replications: 2, seed: 42,
  });
  const [limits, setLimits] = useState<SimulationLimits | null>(null);
  const [run, setRun] = useState<SimulationRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { getSimulationLimits().then(setLimits).catch(() => setLimits(null)); }, []);

  // The optimiser solves one policy per car per time slot per repetition (see backend/api/simulation.py).
  const work = p.num_evs * p.n_replications * p.horizon_slots;
  const overBudget = limits !== null && Number.isFinite(work) && work > limits.max_work;
  const minutes = limits && Number.isFinite(work) ? work / limits.solves_per_second_cold / 60 : null;

  const set = <K extends keyof SimulationParams>(k: K, v: SimulationParams[K]) => setP((s) => ({ ...s, [k]: v }));

  async function start() {
    setBusy(true); setError(null);
    try { setRun(await runSimulation(p)); }
    catch (e) { setRun(null); setError(errorMessage(e)); }
    finally { setBusy(false); }
  }

  const metricKeys = run?.results[0] ? Object.keys(run.results[0].metrics) : [];

  return (
    <>
      <PageHead title="Policy simulator">
        Run the same simulated fleet under several charging policies and compare the outcomes. Each policy
        is repeated with different random conditions; the whisker on each bar is the 95% confidence interval.
      </PageHead>

      <Card>
        <div className="grid cols-4">
          <NumberField label="Cars" value={p.num_evs} onChange={(v) => set("num_evs", Math.round(v))} min={1} max={500} />
          <NumberField label="Chargers" value={p.num_chargers} onChange={(v) => set("num_chargers", Math.round(v))} min={1} max={100} />
          <NumberField label="Charger power" value={p.charger_power_kw} onChange={(v) => set("charger_power_kw", v)} min={1} suffix="kW" />
          <NumberField label="Grid capacity" value={p.grid_capacity_kw} onChange={(v) => set("grid_capacity_kw", v)} min={1} suffix="kW" />
          <NumberField label="Time slots" value={p.horizon_slots} onChange={(v) => set("horizon_slots", Math.round(v))} min={1} max={200} />
          <NumberField label="Repetitions" value={p.n_replications} onChange={(v) => set("n_replications", Math.round(v))} min={1} max={20} hint="More is more reliable, but slower." />
          <NumberField label="Random seed" value={p.seed} onChange={(v) => set("seed", Math.round(v))} hint="Same seed, same result." />
          <div className="field" style={{ justifyContent: "flex-end" }}>
            <button className="btn" onClick={start} disabled={busy || !allFinite(p) || overBudget}>{busy ? "Simulating" : "Run comparison"}</button>
          </div>
        </div>
      </Card>

      <div className="stack" style={{ marginTop: 22 }}>
        {limits && Number.isFinite(work) && (overBudget
          ? <Notice tone="warn">
              This setup needs about {work.toLocaleString()} optimiser calculations, over the limit of {limits.max_work.toLocaleString()}.
              Reduce the cars, repetitions or time slots (calculations = cars × repetitions × time slots).
            </Notice>
          : <p style={{ fontSize: 13, color: "var(--text-muted)" }}>
              About {work.toLocaleString()} optimiser calculations. A first run takes up to {minutes! < 1 ? "a minute" : `${Math.ceil(minutes!)} min`};
              repeating the same setup is much faster because results are cached.
            </p>)}
        {busy && <Notice>Running {p.n_replications} repetitions for every policy. Keep this tab open.</Notice>}
        {error && <Notice tone="error">{error}</Notice>}
        {run && (
          <Card title="Results" aside={<SourceBadge source="simulated" />}>
            {metricKeys.map((key) => {
              const hib = higherIsBetter(key);
              const rows: MetricRow[] = run.results.map((r) => {
                const m = r.metrics[key];
                return { label: humanise(r.algorithm), mean: m.mean, lo: m.ci95_low, hi: m.ci95_high, best: false };
              });
              const target = hib ? Math.max(...rows.map((r) => r.mean)) : Math.min(...rows.map((r) => r.mean));
              rows.forEach((r) => { r.best = r.mean === target; });
              return (
                <div className="metric" key={key}>
                  <div className="metric-head"><h3>{humanise(key)}</h3><span>{hib ? "Higher is better" : "Lower is better"}</span></div>
                  <MetricBars rows={rows} />
                </div>
              );
            })}
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>Experiment {run.experiment_id}. Simulated fleet, not live data.</p>
          </Card>
        )}
      </div>
    </>
  );
}
