"use client";
import { useEffect, useState } from "react";
import LineChart from "@/charts/LineChart";
import { ConditionControls, PolicyControls } from "@/components/PolicyControls";
import { Card, PageHead, Notice, SelectField } from "@/components/ui";
import { useRun } from "@/hooks/useRun";
import { runSensitivity, type Sensitivity, type SweepName } from "@/services/api";
import { DEFAULT_CONDITIONS, SHORT_POLICY } from "@/services/defaults";

const SWEEPS: { value: SweepName; label: string; blurb: string }[] = [
  { value: "soc", label: "Battery level", blurb: "How the recommended power changes as the battery fills." },
  { value: "price", label: "Electricity price", blurb: "Does a higher price make the optimiser charge more gently?" },
  { value: "grid", label: "Grid load", blurb: "Does a stressed grid make it back off?" },
  { value: "solar", label: "Solar availability", blurb: "Does plentiful solar make it charge harder?" },
  { value: "profile", label: "Optimisation profile", blurb: "Same situation, five different priorities." },
  { value: "cost_weight", label: "Weight on cost", blurb: "Scale how much the profile cares about money (0.25x to 4x)." },
];

export default function SensitivityPage() {
  const [policy, setPolicy] = useState(SHORT_POLICY);
  const [cond, setCond] = useState(DEFAULT_CONDITIONS);
  const [sweep, setSweep] = useState<SweepName>("price");
  const { data, error, busy, run } = useRun<Sensitivity>();
  const go = (s: SweepName = sweep) => run(() => runSensitivity({ ...policy, ...cond, sweep: s }));
  useEffect(() => { void go(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const stateSweep = data && ["price", "grid", "solar"].includes(data.sweep);
  const info = SWEEPS.find((s) => s.value === sweep);

  return (
    <>
      <PageHead title="Sensitivity analysis">
        Change one input at a time and watch the optimiser&apos;s recommendation for the first time slot. A sensible policy is monotone:
        it should not charge harder when electricity gets dearer or the grid gets more stressed.
      </PageHead>
      <div className="split">
        <Card title="Settings">
          <div className="stack">
            <SelectField label="Vary" value={sweep} onChange={(v) => { setSweep(v); void go(v); }} options={SWEEPS.map((s) => ({ value: s.value, label: s.label }))} hint={info?.blurb} />
            <PolicyControls value={policy} onChange={setPolicy} />
            <ConditionControls value={cond} onChange={setCond} />
            <button className="btn" onClick={() => void go()} disabled={busy}>{busy ? "Solving" : "Run sweep"}</button>
            <p className="hint" style={{ fontSize: 12, color: "var(--text-muted)" }}>A short look-ahead (8 slots) is the default: with hours to spare the optimiser can almost always wait, which makes every curve flat.</p>
          </div>
        </Card>
        <div className="stack">
          {error && <Notice tone="error">{error}</Notice>}
          {data && (
            <>
              <Card title="Recommended charging power now">
                <LineChart xTitle={data.x_label} yTitle="Power (kW)" step={!!stateSweep}
                  series={[{ name: "Recommended power", color: "var(--current)", step: !!stateSweep,
                    points: data.points.map((p) => ({ x: p.x, y: p.action_kw, note: p.level ? `${p.label} (${p.level})` : p.label })) }]} />
              </Card>
              <Card title="Expected total cost from here (value function)">
                <LineChart xTitle={data.x_label} yTitle="Cost-to-go" series={[{ name: "Value function", color: "var(--signal)", points: data.points.map((p) => ({ x: p.x, y: p.value, note: p.label })) }]} />
              </Card>
              <p className="hint" style={{ fontSize: 12, color: "var(--text-muted)" }}>{data.note}</p>
            </>
          )}
        </div>
      </div>
    </>
  );
}
