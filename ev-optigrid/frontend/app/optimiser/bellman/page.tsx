"use client";
import { useEffect, useState } from "react";
import { PolicyControls } from "@/components/PolicyControls";
import { Card, NumberField, PageHead, Notice, SelectField, Stat } from "@/components/ui";
import { useRun } from "@/hooks/useRun";
import { getBellman, type Bellman } from "@/services/api";
import { LEVELS, SHORT_POLICY, SOLAR_LEVELS } from "@/services/defaults";

const f = (n: number) => n.toFixed(4);

export default function BellmanPage() {
  const [policy, setPolicy] = useState(SHORT_POLICY);
  const [state, setState] = useState({ t: 0, soc_pct: 40, price_level: 1, grid_level: 1, solar_level: 1 });
  const { data, error, busy, run } = useRun<Bellman>();
  const go = () => run(() => getBellman({ ...policy, ...state }));
  useEffect(() => { void go(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const maxQ = data ? Math.max(...data.actions.map((a) => a.q_value)) : 1;
  const minQ = data ? Math.min(...data.actions.map((a) => a.q_value)) : 0;

  return (
    <>
      <PageHead title="Bellman equation">
        The optimiser chooses the action with the lowest total cost: what this slot costs now, plus the discounted cost of the best that can be done afterwards.
        Below, that calculation is redone for one state, action by action, and checked against the solver&apos;s own answer.
      </PageHead>
      <div className="split">
        <Card title="Pick a state">
          <div className="stack">
            <PolicyControls value={policy} onChange={setPolicy} compact />
            <NumberField label="Look ahead" value={policy.horizon_slots} onChange={(v) => setPolicy({ ...policy, horizon_slots: Math.round(v) })} min={2} max={96} suffix="slots" />
            <NumberField label="Time slot" value={state.t} onChange={(v) => setState((s) => ({ ...s, t: Math.max(0, Math.round(v)) }))} min={0} max={policy.horizon_slots - 1} hint="0 is now; the last slot is just before the deadline." />
            <NumberField label="Battery level" value={state.soc_pct} onChange={(v) => setState((s) => ({ ...s, soc_pct: v }))} min={0} max={100} suffix="%" />
            <SelectField label="Price" value={String(state.price_level)} onChange={(v) => setState((s) => ({ ...s, price_level: Number(v) }))} options={LEVELS.map((n, i) => ({ value: String(i), label: n }))} />
            <SelectField label="Grid load" value={String(state.grid_level)} onChange={(v) => setState((s) => ({ ...s, grid_level: Number(v) }))} options={LEVELS.map((n, i) => ({ value: String(i), label: n }))} />
            <SelectField label="Solar" value={String(state.solar_level)} onChange={(v) => setState((s) => ({ ...s, solar_level: Number(v) }))} options={SOLAR_LEVELS.map((n, i) => ({ value: String(i), label: n }))} />
            <button className="btn" onClick={() => void go()} disabled={busy}>{busy ? "Calculating" : "Calculate"}</button>
          </div>
        </Card>

        <div className="stack">
          {error && <Notice tone="error">{error}</Notice>}
          {data && (
            <>
              <Card title="The equation">
                <div className="formula">
                  <strong>V</strong>(s) = min<sub>a</sub> [ <em>C</em>(s, a) + γ · Σ P(s′ | s, a) · <strong>V</strong>(s′) ]<br />
                  <span style={{ color: "var(--text-muted)" }}>C = w·electricity + w·battery wear + w·grid stress − w·renewable reward, γ = {data.gamma}</span>
                </div>
                {data.next_is_terminal && <p className="prose" style={{ marginTop: 12, fontSize: 13 }}>This is the last slot, so the future term is the penalty for missing the target and safe battery level at the deadline.</p>}
              </Card>

              <Notice tone={data.matches_solver ? "good" : "error"}>
                {data.matches_solver
                  ? `Check passed: the best action here is ${data.best_action_kw} kW, the same as the solver's policy, and the minimum Q-value (${f(data.min_q)}) equals the solver's value function (${f(data.solver_value_function)}).`
                  : `Mismatch with the solver (difference ${data.residual.toExponential(2)}). This should not happen; please report it.`}
              </Notice>

              <Card title={`Every charging power, from battery ${data.state.soc_pct}% (price ${data.state.price_level}, grid ${data.state.grid_level}, solar ${data.state.solar_level})`}>
                <div className="table-wrap"><table>
                  <thead><tr>
                    <th className="num">Power</th><th className="num">Battery after</th><th className="num">Electricity</th><th className="num">Battery wear</th>
                    <th className="num">Grid stress</th><th className="num">Renewable</th><th className="num">Cost now</th><th className="num">γ · future</th><th>Total Q(s, a)</th>
                  </tr></thead>
                  <tbody>
                    {data.actions.map((a) => (
                      <tr key={a.action_kw} className={a.is_best ? "best" : ""}>
                        <td className="num">{a.action_kw} kW</td><td className="num">{a.soc_after_pct.toFixed(1)}%</td>
                        <td className="num">{f(a.immediate_cost.electricity)}</td><td className="num">{f(a.immediate_cost.degradation)}</td>
                        <td className="num">{f(a.immediate_cost.grid)}</td><td className="num">{f(a.immediate_cost.renewable)}</td>
                        <td className="num">{f(a.immediate_cost.total)}</td><td className="num">{f(a.discounted_future_value)}</td>
                        <td><div className="score"><span className="bar-inline" style={{ width: `${20 + 80 * ((a.q_value - minQ) / (maxQ - minQ || 1))}px`, opacity: a.is_best ? 1 : 0.45 }} /><span className="mono">{f(a.q_value)}</span></div></td>
                      </tr>
                    ))}
                  </tbody>
                </table></div>
                <p className="prose" style={{ marginTop: 12, fontSize: 13 }}>
                  Highlighted row is the minimum. The renewable column is negative because charging when solar is plentiful is rewarded.
                  Cost now + γ · future = Q, which is what the optimiser compares.
                </p>
              </Card>

              <div className="grid cols-3">
                <Card><Stat label="Best action" value={data.best_action_kw} unit="kW" tone="good" /></Card>
                <Card><Stat label="Solver's action" value={data.solver_policy_action_kw} unit="kW" /></Card>
                <Card><Stat label="Difference from solver" value={data.residual.toExponential(1)} tone={data.matches_solver ? "good" : "bad"} /></Card>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
