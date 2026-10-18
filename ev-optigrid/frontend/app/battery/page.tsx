"use client";
import { useEffect, useState } from "react";
import LineChart from "@/charts/LineChart";
import { Card, NumberField, PageHead, Notice } from "@/components/ui";
import { useRun } from "@/hooks/useRun";
import { getBatteryCurves, type BatteryCurves, type WearPoint } from "@/services/api";

const COMPONENTS: { key: keyof WearPoint["components"]; name: string; color: string }[] = [
  { key: "charge_rate", name: "Charging speed", color: "var(--current)" },
  { key: "high_soc_exposure", name: "Time spent nearly full", color: "var(--signal)" },
  { key: "depth_of_discharge", name: "Size of the swing", color: "var(--renewable)" },
  { key: "temperature", name: "Temperature", color: "var(--urgent)" },
];

function WearChart({ block, title }: { block: BatteryCurves["by_charge_power"]; title: string }) {
  return (
    <Card title={title} aside={<span className="badge">{block.window}</span>}>
      <LineChart xTitle={block.x_label} yTitle="Wear per charge" yMin={0}
        series={[{ name: "Total wear", color: "var(--text-primary)", points: block.points.map((p) => ({ x: p.x, y: p.total })) },
          ...COMPONENTS.map((c) => ({ name: c.name, color: c.color, points: block.points.map((p) => ({ x: p.x, y: p.components[c.key] })) }))]} />
    </Card>
  );
}

export default function BatteryPage() {
  const [maxKw, setMaxKw] = useState(50);
  const [temp, setTemp] = useState(25);
  const { data, error, run } = useRun<BatteryCurves>();
  useEffect(() => {
    if (!Number.isFinite(maxKw) || !Number.isFinite(temp) || maxKw <= 0) return;
    const t = setTimeout(() => void run(() => getBatteryCurves({ max_charge_rate_kw: maxKw, ambient_temp_c: temp })), 250);
    return () => clearTimeout(t);
  }, [maxKw, temp, run]);

  return (
    <>
      <PageHead title="Battery health">
        Charging is not free for the battery. The optimiser adds a wear cost to every charging decision, made of four parts: how fast you charge,
        how long the battery sits nearly full, how big the swing is, and how hot or cold it is. Here is each part on its own.
      </PageHead>
      <Card title="Your battery">
        <div className="grid cols-3">
          <NumberField label="Max charging speed" value={maxKw} onChange={setMaxKw} min={1} suffix="kW" />
          <NumberField label="Ambient temperature" value={temp} onChange={setTemp} min={-40} max={60} suffix="°C" />
        </div>
      </Card>
      <div className="stack" style={{ marginTop: 22 }}>
        {error && <Notice tone="error">{error}</Notice>}
        {data && (
          <>
            <WearChart block={data.by_charge_power} title="Wear against charging speed" />
            <WearChart block={data.by_end_soc} title="Wear against how full you charge" />
            <WearChart block={data.by_temperature} title="Wear against temperature" />
            <Card title="Health indicator">
              <LineChart xTitle={data.health_indicator.x_label} yTitle="Health (%)" yMin={0} yMax={100}
                series={[{ name: "Health", color: "var(--renewable)", points: data.health_indicator.points.map((p) => ({ x: p.x, y: p.health_pct })) }]} />
            </Card>
            <p className="hint" style={{ fontSize: 12, color: "var(--text-muted)" }}>
              Weights: speed {data.weights.k_charge_rate}, nearly-full {data.weights.k_high_soc}, swing {data.weights.k_dod}, temperature {data.weights.k_temperature}. {data.note}
            </p>
          </>
        )}
      </div>
    </>
  );
}
