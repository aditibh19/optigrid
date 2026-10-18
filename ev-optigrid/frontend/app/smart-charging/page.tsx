"use client";
import { useState } from "react";
import MonitorPanel from "@/components/MonitorPanel";
import { Card, NumberField, SelectField, PageHead, Notice, Stat, allFinite, errorMessage, CURRENCY } from "@/components/ui";
import { optimizeCharging, predictGrid, predictPrice, type OptimizeRequest, type OptimizeResponse, type Profile } from "@/services/api";

const PROFILES: { value: Profile; label: string }[] = [
  { value: "balanced", label: "Balanced" },
  { value: "save_money", label: "Save money" },
  { value: "fastest", label: "Fastest" },
  { value: "battery_health", label: "Protect battery health" },
  { value: "green", label: "Use more renewable energy" },
];

const DEFAULTS: OptimizeRequest = {
  battery_capacity_kwh: 60, max_charge_rate_kw: 50, current_soc_pct: 32, target_soc_pct: 90,
  minimum_safe_soc_pct: 70, horizon_slots: 24, slot_minutes: 15, current_price_per_kwh: 8,
  current_grid_load_pct: 60, current_solar_availability_frac: 0.2, profile: "balanced",
};

function verdictOf(r: OptimizeResponse) {
  switch (r.recommended_action) {
    case "charge_now": return { kind: "charge", title: `Charge now at ${r.action_kw} kW` };
    case "wait": return { kind: "wait", title: "Hold off on charging for now" };
    case "no_action_needed": return { kind: "done", title: "No charging needed" };
    default: return { kind: "charge", title: `Charge at reduced power, ${r.action_kw} kW` };
  }
}

export default function SmartChargingPage() {
  const [form, setForm] = useState<OptimizeRequest>(DEFAULTS);
  const [result, setResult] = useState<OptimizeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [baseline, setBaseline] = useState<OptimizeRequest | null>(null);   // conditions the current plan was made under

  const set = <K extends keyof OptimizeRequest>(k: K, v: OptimizeRequest[K]) => setForm((f) => ({ ...f, [k]: v }));

  async function submit() {
    setBusy(true); setError(null);
    try { setResult(await optimizeCharging(form)); setBaseline({ ...form }); }
    catch (e) { setResult(null); setError(errorMessage(e)); }
    finally { setBusy(false); }
  }

  async function fillFromForecasts() {
    setError(null); setNote(null);
    try {
      const [price, grid] = await Promise.all([predictPrice(), predictGrid()]);
      setForm((f) => ({
        ...f,
        current_price_per_kwh: Math.round(price.predicted_price_per_kwh * 100) / 100,
        current_grid_load_pct: Math.round(grid.predicted_grid_load_pct * 10) / 10,
      }));
      setNote("Price and grid load filled in from the model forecasts.");
    } catch (e) { setError(errorMessage(e)); }
  }

  const v = result ? verdictOf(result) : null;
  const valid = allFinite(form);

  return (
    <>
      <PageHead title="Smart charging">
        Tell the optimiser about your car and the conditions right now. It looks ahead across the
        next {Number.isFinite(form.horizon_slots * form.slot_minutes) ? (form.horizon_slots * form.slot_minutes) / 60 : "few"} hours
        and recommends what to do in this time slot.
      </PageHead>

      <div className="split">
        <div className="stack">
          <Card title="Your car">
            <div className="stack">
              <div className="two">
                <NumberField label="Charge now" value={form.current_soc_pct} onChange={(x) => set("current_soc_pct", x)} min={0} max={100} suffix="%" />
                <NumberField label="Charge wanted" value={form.target_soc_pct} onChange={(x) => set("target_soc_pct", x)} min={0} max={100} suffix="%" />
              </div>
              <NumberField label="Never go below" value={form.minimum_safe_soc_pct} onChange={(x) => set("minimum_safe_soc_pct", x)} min={0} max={100} suffix="%" hint="Your safety reserve for the trip." />
              <div className="two">
                <NumberField label="Battery size" value={form.battery_capacity_kwh} onChange={(x) => set("battery_capacity_kwh", x)} min={1} suffix="kWh" />
                <NumberField label="Max charging speed" value={form.max_charge_rate_kw} onChange={(x) => set("max_charge_rate_kw", x)} min={1} suffix="kW" />
              </div>
            </div>
          </Card>

          <Card title="Conditions" aside={<button className="btn ghost small" onClick={fillFromForecasts}>Use forecasts</button>}>
            <div className="stack">
              <div className="two">
                <NumberField label="Electricity price" value={form.current_price_per_kwh} onChange={(x) => set("current_price_per_kwh", x)} min={0} suffix={`${CURRENCY}/kWh`} />
                <NumberField label="Grid load" value={form.current_grid_load_pct} onChange={(x) => set("current_grid_load_pct", x)} min={0} max={100} suffix="%" />
              </div>
              <NumberField label="Solar availability" value={form.current_solar_availability_frac} onChange={(x) => set("current_solar_availability_frac", x)} min={0} max={1} step={0.05} hint="0 means none, 1 means full sun." />
              <SelectField label="What matters most" value={form.profile} onChange={(x) => set("profile", x)} options={PROFILES} />
              <div className="two">
                <NumberField label="Look ahead" value={form.horizon_slots} onChange={(x) => set("horizon_slots", Math.round(x))} min={1} max={200} suffix="slots" />
                <NumberField label="Slot length" value={form.slot_minutes} onChange={(x) => set("slot_minutes", Math.round(x))} min={1} max={120} suffix="min" />
              </div>
              {note && <Notice tone="good">{note}</Notice>}
              <button className="btn" onClick={submit} disabled={busy || !valid}>{busy ? "Working it out" : "Get recommendation"}</button>
              {!valid && <span className="hint" style={{ color: "var(--text-muted)", fontSize: 12 }}>Fill in every field to continue.</span>}
            </div>
          </Card>
        </div>

        <div className="stack">
          {error && <Notice tone="error">{error}</Notice>}
          {!result && !error && (
            <Card><p className="empty">Your recommendation will appear here, with the reasons behind it.</p></Card>
          )}
          {result && v && (
            <>
              <Card>
                <div className={`verdict ${v.kind}`}>
                  <h2>{v.title}</h2>
                  <p>{result.explanation_paragraph}</p>
                </div>
              </Card>
              {!result.is_feasible && (
                <Notice tone="warn">
                  The target can&apos;t be reached in the look-ahead window. The best possible is {result.max_achievable_soc_pct}%
                  even at full power. Try a longer window or a lower target.
                </Notice>
              )}
              <Card title="This time slot">
                <div className="grid cols-3">
                  <Stat label={`Cost of this ${form.slot_minutes}-minute slot`} value={`${CURRENCY}${result.estimated_cost.toFixed(2)}`} tone={result.estimated_cost === 0 ? "warn" : undefined} />
                  <Stat label="Same slot at full power" value={`${CURRENCY}${result.immediate_cost.toFixed(2)}`} />
                  <Stat label="Best reachable charge" value={result.max_achievable_soc_pct} unit="%" tone={result.is_feasible ? "good" : "bad"} />
                </div>
                <p className="hint" style={{ marginTop: 14, fontSize: 12, color: "var(--text-muted)" }}>
                  These are costs for one slot, not for the whole charge. Waiting costs {CURRENCY}0 now because the charging is planned for a later slot.
                </p>
              </Card>
              {baseline && (
                <MonitorPanel key={JSON.stringify(baseline)} baseline={baseline}
                  onAdopt={(now, plan) => { setForm(now); setResult(plan); setBaseline({ ...now }); }} />
              )}
              <Card title="Why this recommendation">
                {result.reasons.map((r) => (
                  <div className="reason" key={r.reason_code}>
                    <span>{r.reason_text}</span>
                    {r.supporting_value !== null && <span className="val">{r.supporting_value.toFixed(2)}</span>}
                    <span className="code">{r.reason_code}</span>
                  </div>
                ))}
              </Card>
            </>
          )}
        </div>
      </div>
    </>
  );
}
