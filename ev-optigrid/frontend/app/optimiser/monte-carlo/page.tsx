"use client";
import { useEffect, useState } from "react";
import Histogram from "@/charts/Histogram";
import { ConditionControls, PolicyControls } from "@/components/PolicyControls";
import { Card, NumberField, PageHead, Notice, CURRENCY } from "@/components/ui";
import { useRun } from "@/hooks/useRun";
import { runMonteCarlo, type MonteCarlo } from "@/services/api";
import { DEFAULT_CONDITIONS, POLICY_COLOR, POLICY_LABEL, SHORT_POLICY } from "@/services/defaults";

export default function MonteCarloPage() {
  const [policy, setPolicy] = useState(SHORT_POLICY);
  const [cond, setCond] = useState(DEFAULT_CONDITIONS);
  const [extra, setExtra] = useState({ n_runs: 500, seed: 42 });
  const { data, error, busy, run } = useRun<MonteCarlo>();
  const go = () => run(() => runMonteCarlo({ ...policy, ...cond, ...extra }));
  useEffect(() => { void go(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const names = data ? Object.keys(data.policies) : [];
  const paired = data?.paired_vs.charge_immediately;
  const sdp = data?.policies.sdp, fast = data?.policies.charge_immediately;

  return (
    <>
      <PageHead title="Monte Carlo">
        Prices, grid load and solar are uncertain, so one run proves little. Here the same charging session is simulated hundreds of times
        under random conditions, for three policies on identical scenarios, and the outcomes are compared as distributions.
      </PageHead>
      <div className="split">
        <Card title="Settings">
          <div className="stack">
            <PolicyControls value={policy} onChange={setPolicy} />
            <ConditionControls value={cond} onChange={setCond} />
            <div className="two">
              <NumberField label="Simulated sessions" value={extra.n_runs} onChange={(v) => setExtra((s) => ({ ...s, n_runs: Math.round(v) }))} min={10} max={2000} />
              <NumberField label="Random seed" value={extra.seed} onChange={(v) => setExtra((s) => ({ ...s, seed: Math.round(v) }))} hint="Same seed, same result." />
            </div>
            <button className="btn" onClick={() => void go()} disabled={busy}>{busy ? "Simulating" : "Run simulation"}</button>
          </div>
        </Card>

        <div className="stack">
          {error && <Notice tone="error">{error}</Notice>}
          {data && paired && sdp && fast && (
            <>
              <Card title={`Result over ${data.n_runs.toLocaleString()} scenarios`}>
                <p style={{ fontSize: 18, lineHeight: 1.5, maxWidth: "58ch" }}>
                  Compared with charging immediately, the optimised plan cost <strong style={{ color: "var(--renewable)" }}>{CURRENCY}{paired.mean_saving_inr.toFixed(0)} less</strong> on
                  average (95% confidence interval {CURRENCY}{paired.ci95_low.toFixed(0)} to {CURRENCY}{paired.ci95_high.toFixed(0)}) and was cheaper in {paired.sdp_cheaper_pct.toFixed(0)}% of scenarios.
                </p>
                <div style={{ marginTop: 16 }}>
                  <Notice tone={sdp.target_met_pct < 50 ? "warn" : "info"}>
                    The trade-off: the optimised plan reached the {policy.target_soc_pct}% target in {sdp.target_met_pct.toFixed(0)}% of scenarios
                    (charging immediately: {fast.target_met_pct.toFixed(0)}%), and stayed above the {policy.minimum_safe_soc_pct}% safe level in {sdp.safe_soc_met_pct.toFixed(0)}%.
                    It saves money by accepting a lower final charge when the profile allows it. Choose &ldquo;Fastest&rdquo; or a longer look-ahead to change that.
                  </Notice>
                </div>
              </Card>

              <Card title="Policies compared">
                <div className="table-wrap"><table>
                  <thead><tr><th>Policy</th><th className="num">Mean cost</th><th className="num">Cost, 5th to 95th</th><th className="num">Mean final charge</th><th className="num">Target met</th><th className="num">Safe level met</th><th className="num">Battery wear</th></tr></thead>
                  <tbody>{names.map((n) => { const p = data.policies[n]; return (
                    <tr key={n} className={n === "sdp" ? "best" : ""}>
                      <td>{POLICY_LABEL[n] ?? n}</td><td className="num">{CURRENCY}{p.cost_inr.mean.toFixed(0)}</td>
                      <td className="num">{CURRENCY}{p.cost_inr.p05.toFixed(0)} to {CURRENCY}{p.cost_inr.p95.toFixed(0)}</td><td className="num">{p.final_soc_pct.mean.toFixed(1)}%</td>
                      <td className="num">{p.target_met_pct.toFixed(0)}%</td><td className="num">{p.safe_soc_met_pct.toFixed(0)}%</td><td className="num">{p.degradation.mean.toFixed(3)}</td>
                    </tr>); })}</tbody>
                </table></div>
              </Card>

              <Card title="Distribution of cost">
                <Histogram edges={data.histograms.cost_inr.edges} counts={data.histograms.cost_inr.counts} colors={POLICY_COLOR} labels={POLICY_LABEL} xTitle={`Cost per session (${CURRENCY})`} />
              </Card>
              <Card title="Distribution of final battery level">
                <Histogram edges={data.histograms.final_soc_pct.edges} counts={data.histograms.final_soc_pct.counts} colors={POLICY_COLOR} labels={POLICY_LABEL} xTitle="Final battery level (%)" />
              </Card>
              <p className="hint" style={{ fontSize: 12, color: "var(--text-muted)" }}>{data.note}</p>
            </>
          )}
        </div>
      </div>
    </>
  );
}
