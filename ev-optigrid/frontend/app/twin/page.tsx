"use client";
import { useEffect, useState } from "react";
import LineChart from "@/charts/LineChart";
import { ConditionControls, PolicyControls } from "@/components/PolicyControls";
import TwinLane from "@/components/TwinLane";
import { Card, NumberField, PageHead, Notice, Stat, CURRENCY } from "@/components/ui";
import { useRun } from "@/hooks/useRun";
import { runTwin, type Twin } from "@/services/api";
import { DEFAULT_CONDITIONS, SHORT_POLICY } from "@/services/defaults";

export default function TwinPage() {
  const [policy, setPolicy] = useState({ ...SHORT_POLICY, horizon_slots: 16 });
  const [cond, setCond] = useState(DEFAULT_CONDITIONS);
  const [seed, setSeed] = useState(7);
  const [i, setI] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const { data, error, busy, run } = useRun<Twin>();

  const go = (s = seed) => { setPlaying(false); setI(0); return run(() => runTwin({ ...policy, ...cond, seed: s })); };
  useEffect(() => { void go(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const last = data ? data.lanes.sdp.records.length - 1 : 0;
  useEffect(() => {
    if (!playing || !data) return;
    const t = setInterval(() => setI((k) => { if (k >= last) { setPlaying(false); return k; } return k + 1; }), 900 / speed);
    return () => clearInterval(t);
  }, [playing, speed, last, data]);

  const cfg = data?.config;
  const sdp = data?.lanes.sdp, fast = data?.lanes.charge_immediately;
  const series = (lane: NonNullable<typeof sdp>, name: string, color: string, key: "soc_after_pct" | "delivered_kw", step = false) =>
    ({ name, color, step, points: lane.records.map((r) => ({ x: +(((r.t + 1) * (cfg?.slot_minutes ?? 15)) / 60).toFixed(2), y: r[key] })) });

  return (
    <>
      <PageHead title="Digital twin">
        A virtual charging session, one time slot at a time. Two identical cars face the same simulated prices, grid load and sunshine;
        one follows the optimiser, the other simply charges at full power until it is full.
      </PageHead>

      <div className="split">
        <Card title="Scenario">
          <div className="stack">
            <PolicyControls value={policy} onChange={setPolicy} />
            <ConditionControls value={cond} onChange={setCond} />
            <NumberField label="Scenario number" value={seed} onChange={(v) => setSeed(Math.round(v))} hint="Each number is a different sequence of prices and grid load." />
            <div className="row">
              <button className="btn" onClick={() => void go()} disabled={busy}>{busy ? "Building" : "Build scenario"}</button>
              <button className="btn ghost" disabled={busy} onClick={() => { const s = Math.floor(Math.random() * 1000); setSeed(s); void go(s); }}>Random scenario</button>
            </div>
          </div>
        </Card>

        <div className="stack">
          {error && <Notice tone="error">{error}</Notice>}
          {data && cfg && sdp && fast && (
            <>
              <Card>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <div className="row">
                    <button className="btn" onClick={() => { if (i >= last) setI(0); setPlaying((p) => !p); }}>{playing ? "Pause" : i >= last ? "Replay" : "Play"}</button>
                    <button className="btn ghost small" onClick={() => setSpeed((s) => (s >= 4 ? 1 : s * 2))} aria-label="Change speed">Speed {speed}x</button>
                  </div>
                  <span className="mono" style={{ color: "var(--text-secondary)" }}>
                    Slot {i + 1} of {last + 1}, {String(Math.floor(((i * cfg.slot_minutes) / 60))).padStart(2, "0")}:{String((i * cfg.slot_minutes) % 60).padStart(2, "0")} from start
                  </span>
                </div>
                <input type="range" min={0} max={last} value={i} onChange={(e) => { setPlaying(false); setI(Number(e.target.value)); }}
                  aria-label="Time slot" style={{ width: "100%", marginTop: 14, accentColor: "#8B7BFA" }} />
              </Card>

              <div className="grid cols-2">
                <TwinLane title="Optimised (SDP)" accent="var(--current)" rec={sdp.records[i]} maxKw={cfg.max_charge_rate_kw} target={cfg.target_soc_pct} safe={cfg.minimum_safe_soc_pct} capacityKwh={cfg.battery_capacity_kwh} />
                <TwinLane title="Charge immediately" accent="var(--gold)" rec={fast.records[i]} maxKw={cfg.max_charge_rate_kw} target={cfg.target_soc_pct} safe={cfg.minimum_safe_soc_pct} capacityKwh={cfg.battery_capacity_kwh} />
              </div>

              <Card title="Whole session">
                <div className="grid cols-4" style={{ marginBottom: 20 }}>
                  <Stat label="Optimised cost" value={`${CURRENCY}${sdp.cost_inr.toFixed(0)}`} tone="good" />
                  <Stat label="Charge-immediately cost" value={`${CURRENCY}${fast.cost_inr.toFixed(0)}`} />
                  <Stat label="Optimised final charge" value={sdp.final_soc_pct.toFixed(0)} unit="%" tone={sdp.final_soc_pct >= cfg.target_soc_pct ? "good" : "warn"} />
                  <Stat label="Charge-immediately final" value={fast.final_soc_pct.toFixed(0)} unit="%" />
                </div>
                <LineChart xTitle="Hours from start" yTitle="Battery level (%)" yMin={0} yMax={100}
                  series={[series(sdp, "Optimised (SDP)", "var(--current)", "soc_after_pct"), series(fast, "Charge immediately", "var(--gold)", "soc_after_pct")]} />
                <div style={{ height: 14 }} />
                <LineChart xTitle="Hours from start" yTitle="Charging power (kW)" step
                  series={[series(sdp, "Optimised (SDP)", "var(--current)", "delivered_kw", true), series(fast, "Charge immediately", "var(--gold)", "delivered_kw", true)]} />
                <p className="hint" style={{ marginTop: 10, fontSize: 12, color: "var(--text-muted)" }}>{data.note}</p>
              </Card>
            </>
          )}
        </div>
      </div>
    </>
  );
}
