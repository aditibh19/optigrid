"use client";
import { useEffect, useState } from "react";
import Heatmap from "@/charts/Heatmap";
import { POWER_STOPS, VALUE_STOPS } from "@/charts/color";
import { PolicyControls } from "@/components/PolicyControls";
import { Card, PageHead, Notice, SelectField } from "@/components/ui";
import { useRun } from "@/hooks/useRun";
import { getPolicyHeatmap, type Heatmap as HeatmapData, type HeatmapRequest } from "@/services/api";
import { DEFAULT_POLICY, LEVELS, SOLAR_LEVELS } from "@/services/defaults";

type View = "soc_by_time" | "price" | "grid" | "solar";

export default function PolicyPage() {
  const [policy, setPolicy] = useState(DEFAULT_POLICY);
  const [view, setView] = useState<View>("soc_by_time");
  const [levels, setLevels] = useState({ price_level: 1, grid_level: 1, solar_level: 1 });
  const [t, setT] = useState(0);
  const [show, setShow] = useState<"action" | "value">("action");
  const { data, error, busy, run } = useRun<HeatmapData>();

  const request = (): HeatmapRequest => ({
    ...policy, mode: view === "soc_by_time" ? "soc_by_time" : "soc_by_level", vary: view === "soc_by_time" ? "price" : view, t, ...levels,
  });
  useEffect(() => { void run(() => getPolicyHeatmap(request())); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const levelSelect = (k: keyof typeof levels, label: string, names: readonly string[]) => (
    <SelectField label={label} value={String(levels[k])} onChange={(v) => setLevels((s) => ({ ...s, [k]: Number(v) }))}
      options={names.map((n, i) => ({ value: String(i), label: n }))} />
  );

  const matrix = data ? (show === "action" ? data.action_kw : data.value) : [];
  const flat = matrix.flat();

  return (
    <>
      <PageHead title="Policy heatmap">
        The optimal policy is a lookup table: for every battery level and time slot, the best charging power. Read across a
        row to see how the plan changes as the deadline approaches, and down a column to see how it depends on the battery level.
      </PageHead>
      <div className="split">
        <Card title="Settings">
          <div className="stack">
            <PolicyControls value={policy} onChange={setPolicy} />
            <SelectField label="Show" value={view} onChange={(v) => setView(v as View)} options={[
              { value: "soc_by_time", label: "Battery level by time slot" }, { value: "price", label: "Battery level by price level" },
              { value: "grid", label: "Battery level by grid load" }, { value: "solar", label: "Battery level by solar" }]} />
            {view !== "soc_by_time" && (
              <div className="field"><label htmlFor="tslot">At time slot</label>
                <div className="input-wrap"><input id="tslot" type="number" min={0} max={policy.horizon_slots - 1} value={t} onChange={(e) => setT(Math.max(0, Number(e.target.value)))} /></div></div>
            )}
            {view !== "price" && levelSelect("price_level", "Price is", LEVELS)}
            {view !== "grid" && levelSelect("grid_level", "Grid load is", LEVELS)}
            {view !== "solar" && levelSelect("solar_level", "Solar is", SOLAR_LEVELS)}
            <SelectField label="Colour by" value={show} onChange={(v) => setShow(v as "action" | "value")} options={[
              { value: "action", label: "Charging power (kW)" }, { value: "value", label: "Expected future cost (value function)" }]} />
            <button className="btn" onClick={() => void run(() => getPolicyHeatmap(request()))} disabled={busy}>{busy ? "Solving" : "Update heatmap"}</button>
          </div>
        </Card>
        <div className="stack">
          {error && <Notice tone="error">{error}</Notice>}
          {data && (
            <Card title={show === "action" ? "Recommended charging power" : "Expected future cost"}>
              <Heatmap matrix={matrix} xLabels={data.x_values} yLabels={data.y_values} xTitle={data.x_label} yTitle="Battery level (%)"
                min={show === "action" ? 0 : Math.min(...flat)} max={show === "action" ? data.max_action_kw : Math.max(...flat)}
                stops={show === "action" ? POWER_STOPS : VALUE_STOPS} unit={show === "action" ? " kW" : ""} decimals={show === "action" ? 0 : 3}
                showValues={data.x_values.length <= 6} />
              <p className="prose" style={{ marginTop: 14, fontSize: 13 }}>
                Price is {data.fixed.price_level}, grid load is {data.fixed.grid_level} and solar is {data.fixed.solar_level}
                {data.fixed.t !== null ? `, at time slot ${data.fixed.t}` : ""} unless that axis is being varied.
                {show === "action" && " The full battery row (100%) is always 0 kW: nothing can be added."}
              </p>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
