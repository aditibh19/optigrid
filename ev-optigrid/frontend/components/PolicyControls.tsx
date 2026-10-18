"use client";
import { NumberField, SelectField } from "@/components/ui";
import type { Conditions, PolicyParams, Profile } from "@/services/api";
import { PROFILE_OPTIONS } from "@/services/defaults";

/** The parameters that define one solved MDP; shared by every "how it decides" page. */
export function PolicyControls({ value, onChange, compact = false }: {
  value: PolicyParams; onChange: (v: PolicyParams) => void; compact?: boolean;
}) {
  const set = <K extends keyof PolicyParams>(k: K, v: PolicyParams[K]) => onChange({ ...value, [k]: v });
  return (
    <div className="stack">
      <SelectField label="What matters most" value={value.profile} onChange={(v) => set("profile", v as Profile)} options={[...PROFILE_OPTIONS]} />
      <div className="two">
        <NumberField label="Battery size" value={value.battery_capacity_kwh} onChange={(v) => set("battery_capacity_kwh", v)} min={1} suffix="kWh" />
        <NumberField label="Max charging speed" value={value.max_charge_rate_kw} onChange={(v) => set("max_charge_rate_kw", v)} min={1} suffix="kW" />
      </div>
      <div className="two">
        <NumberField label="Charge wanted" value={value.target_soc_pct} onChange={(v) => set("target_soc_pct", v)} min={0} max={100} suffix="%" />
        <NumberField label="Never go below" value={value.minimum_safe_soc_pct} onChange={(v) => set("minimum_safe_soc_pct", v)} min={0} max={100} suffix="%" />
      </div>
      {!compact && (
        <div className="two">
          <NumberField label="Look ahead" value={value.horizon_slots} onChange={(v) => set("horizon_slots", Math.round(v))} min={2} max={96} suffix="slots" />
          <NumberField label="Slot length" value={value.slot_minutes} onChange={(v) => set("slot_minutes", Math.round(v))} min={1} max={120} suffix="min" />
        </div>
      )}
    </div>
  );
}

export function ConditionControls({ value, onChange, hide = [] }: {
  value: Conditions; onChange: (v: Conditions) => void; hide?: (keyof Conditions)[];
}) {
  const set = <K extends keyof Conditions>(k: K, v: Conditions[K]) => onChange({ ...value, [k]: v });
  return (
    <div className="stack">
      {!hide.includes("current_soc_pct") && <NumberField label="Charge now" value={value.current_soc_pct} onChange={(v) => set("current_soc_pct", v)} min={0} max={100} suffix="%" />}
      {!hide.includes("current_price_per_kwh") && <NumberField label="Electricity price" value={value.current_price_per_kwh} onChange={(v) => set("current_price_per_kwh", v)} min={0} suffix="₹/kWh" />}
      {!hide.includes("current_grid_load_pct") && <NumberField label="Grid load" value={value.current_grid_load_pct} onChange={(v) => set("current_grid_load_pct", v)} min={0} max={100} suffix="%" />}
      {!hide.includes("current_solar_availability_frac") && <NumberField label="Solar availability" value={value.current_solar_availability_frac} onChange={(v) => set("current_solar_availability_frac", v)} min={0} max={1} step={0.05} hint="0 none, 1 full sun." />}
    </div>
  );
}
