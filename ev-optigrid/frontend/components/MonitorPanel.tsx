"use client";
import { useEffect, useRef, useState } from "react";
import { Card, NumberField, Notice, CURRENCY, errorMessage } from "@/components/ui";
import { monitorConditions, predictGrid, predictPrice, type MonitorResult, type OptimizeRequest, type OptimizeResponse } from "@/services/api";

const ACTION_TEXT: Record<string, string> = { wait: "Wait", charge_now: "Charge now", no_action_needed: "No charging needed", charge_partial: "Charge at reduced power" };
const describe = (r: OptimizeResponse) => `${ACTION_TEXT[r.recommended_action] ?? r.recommended_action}${r.action_kw > 0 ? ` at ${r.action_kw} kW` : ""}`;

/** Monitor -> conditions changed? -> re-optimise (the synopsis workflow), with a before/after view. */
export default function MonitorPanel({ baseline, onAdopt }: { baseline: OptimizeRequest; onAdopt: (now: OptimizeRequest, plan: OptimizeResponse) => void }) {
  const [now, setNow] = useState<OptimizeRequest>(baseline);
  const [queue, setQueue] = useState({ before: 10, now: 10 });
  const [result, setResult] = useState<MonitorResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [watching, setWatching] = useState(false);
  const latest = useRef({ now, queue });
  latest.current = { now, queue };

  async function check(next: OptimizeRequest, q: { before: number; now: number }) {
    setBusy(true); setError(null);
    try {
      setResult(await monitorConditions({ previous: baseline, current: next, previous_queue_wait_min: q.before, current_queue_wait_min: q.now }));
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }

  function apply(patch: Partial<OptimizeRequest>, queueNow?: number) {
    const next = { ...now, ...patch };
    const q = { ...queue, now: queueNow ?? queue.now };
    setNow(next); setQueue(q); void check(next, q);
  }

  // "Watch live forecasts": every 20 s pull fresh price and grid forecasts and re-check.
  useEffect(() => {
    if (!watching) return;
    const tick = async () => {
      try {
        const [p, g] = await Promise.all([predictPrice(), predictGrid()]);
        const next = { ...latest.current.now, current_price_per_kwh: Math.round(p.predicted_price_per_kwh * 100) / 100,
          current_grid_load_pct: Math.round(g.predicted_grid_load_pct * 10) / 10 };
        setNow(next); await check(next, latest.current.queue);
      } catch (e) { setError(errorMessage(e)); }
    };
    void tick();
    const t = setInterval(tick, 20000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watching]);

  const events: { label: string; run: () => void }[] = [
    { label: "Price jumps 50%", run: () => apply({ current_price_per_kwh: Math.round(baseline.current_price_per_kwh * 1.5 * 100) / 100 }) },
    { label: "Grid becomes stressed", run: () => apply({ current_grid_load_pct: Math.min(100, baseline.current_grid_load_pct + 25) }) },
    { label: "Sun comes out", run: () => apply({ current_solar_availability_frac: 0.9 }) },
    { label: "Queue grows by 20 min", run: () => apply({}, queue.before + 20) },
    { label: "Deadline moves 2 hours closer", run: () => apply({ horizon_slots: Math.max(2, baseline.horizon_slots - Math.round(120 / baseline.slot_minutes)) }) },
  ];

  return (
    <Card title="When conditions change" aside={<label className="row" style={{ gap: 8, fontSize: 13, color: "var(--text-secondary)" }}>
      <input type="checkbox" checked={watching} onChange={(e) => setWatching(e.target.checked)} /> Watch live forecasts</label>}>
      <p className="prose" style={{ marginBottom: 14 }}>
        A plan made now can go stale. Trigger a change below, or watch the live forecasts. The system compares the new situation with the one
        this plan was made under and only re-plans when the change is large enough to matter.
      </p>
      <div className="preset-row" style={{ marginBottom: 14 }}>
        {events.map((e) => <button key={e.label} className="chip" disabled={busy} onClick={e.run}>{e.label}</button>)}
        <button className="chip" onClick={() => { setNow(baseline); setQueue({ before: queue.before, now: queue.before }); setResult(null); }}>Reset</button>
      </div>
      <div className="grid cols-4" style={{ marginBottom: 14 }}>
        <NumberField label="Price now" value={now.current_price_per_kwh} onChange={(v) => setNow((s) => ({ ...s, current_price_per_kwh: v }))} min={0} suffix={`${CURRENCY}/kWh`} />
        <NumberField label="Grid load now" value={now.current_grid_load_pct} onChange={(v) => setNow((s) => ({ ...s, current_grid_load_pct: v }))} min={0} max={100} suffix="%" />
        <NumberField label="Station queue now" value={queue.now} onChange={(v) => setQueue((s) => ({ ...s, now: v }))} min={0} suffix="min" hint={`Was ${queue.before} min when planned.`} />
        <div className="field" style={{ justifyContent: "flex-end" }}><button className="btn ghost" disabled={busy} onClick={() => void check(now, queue)}>{busy ? "Checking" : "Check now"}</button></div>
      </div>

      {error && <Notice tone="error">{error}</Notice>}
      {result && (
        <div className="stack">
          {result.changed ? (
            <Notice tone="warn">
              <strong>Conditions changed, so the plan was recomputed.</strong>
              <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>{result.triggers.map((t) => <li key={t.code}>{t.label}</li>)}</ul>
            </Notice>
          ) : (
            <Notice tone="good">No significant change (price {result.thresholds.price_pct}%, grid {result.thresholds.grid_pts} points, queue {result.thresholds.queue_min} min or more would trigger a new plan). The plan stands.</Notice>
          )}
          <div className="grid cols-2">
            <div className="card" style={{ background: "var(--surface-raised)" }}>
              <span className="badge">Before</span>
              <h3 style={{ fontSize: 20, margin: "10px 0 6px" }}>{describe(result.previous)}</h3>
              <p className="prose" style={{ fontSize: 13 }}>Slot cost {CURRENCY}{result.previous.estimated_cost.toFixed(2)}. Best reachable {result.previous.max_achievable_soc_pct}%.</p>
            </div>
            <div className="card" style={{ background: "var(--surface-raised)", borderColor: result.action_changed ? "var(--gold)" : undefined }}>
              <span className={`badge ${result.action_changed ? "demo" : ""}`}>{result.action_changed ? "After: plan changed" : "After: same recommendation"}</span>
              <h3 style={{ fontSize: 20, margin: "10px 0 6px" }}>{describe(result.current)}</h3>
              <p className="prose" style={{ fontSize: 13 }}>Slot cost {CURRENCY}{result.current.estimated_cost.toFixed(2)}. Best reachable {result.current.max_achievable_soc_pct}%.</p>
            </div>
          </div>
          {result.changed && <p className="prose" style={{ fontSize: 13 }}>{result.current.explanation_paragraph}</p>}
          {result.changed && <button className="btn ghost" style={{ alignSelf: "flex-start" }} onClick={() => { onAdopt(now, result.current); setQueue((q) => ({ ...q, before: q.now })); }}>Use these conditions as the new baseline</button>}
        </div>
      )}
    </Card>
  );
}
