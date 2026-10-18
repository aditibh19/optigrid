"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Card, PageHead, SourceBadge, Stat, Notice, errorMessage, CURRENCY } from "@/components/ui";
import { predictGrid, predictPrice, predictQueue, predictSolar,
  type GridForecast, type PriceForecast, type QueueForecast, type SolarForecast } from "@/services/api";

interface Forecasts { price?: PriceForecast; grid?: GridForecast; solar?: SolarForecast; queue?: QueueForecast }

export default function OverviewPage() {
  const [data, setData] = useState<Forecasts | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.allSettled([predictPrice(), predictGrid(), predictSolar(), predictQueue()]).then((r) => {
      if (!alive) return;
      const [price, grid, solar, queue] = r;
      setData({
        price: price.status === "fulfilled" ? price.value : undefined,
        grid: grid.status === "fulfilled" ? grid.value : undefined,
        solar: solar.status === "fulfilled" ? solar.value : undefined,
        queue: queue.status === "fulfilled" ? queue.value : undefined,
      });
      const failed = r.find((x) => x.status === "rejected") as PromiseRejectedResult | undefined;
      if (failed && r.every((x) => x.status === "rejected")) setError(errorMessage(failed.reason));
    });
    return () => { alive = false; };
  }, []);

  const gridTone = (p: number) => (p > 80 ? "bad" : p > 65 ? "warn" : "good");

  return (
    <>
      <PageHead title="Charge when it makes sense, and know why">
        EV-OptiGrid weighs your battery, your trip, electricity prices and grid load, then tells you
        whether to charge now or wait, with the reasons.
      </PageHead>

      {error && <div style={{ marginBottom: 18 }}><Notice tone="error">{error}</Notice></div>}

      <div className="grid cols-4" style={{ marginBottom: 26 }}>
        <Card title="Electricity price" aside={data?.price && <SourceBadge source={data.price.source} />}>
          {data ? (data.price ? <Stat label="Expected this hour" value={`${CURRENCY}${data.price.predicted_price_per_kwh.toFixed(2)}`} unit="/kWh" /> : <span className="empty">Unavailable</span>) : <div className="skeleton" />}
        </Card>
        <Card title="Grid load" aside={data?.grid && <SourceBadge source={data.grid.source} />}>
          {data ? (data.grid ? <Stat label="Expected this hour" tone={gridTone(data.grid.predicted_grid_load_pct)} value={data.grid.predicted_grid_load_pct.toFixed(1)} unit="%" /> : <span className="empty">Unavailable</span>) : <div className="skeleton" />}
        </Card>
        <Card title="Solar output" aside={data?.solar && <SourceBadge source={data.solar.source} />}>
          {data ? (data.solar ? <Stat label="Expected this hour" tone="signal" value={data.solar.predicted_generation_kwh.toFixed(2)} unit="kWh" /> : <span className="empty">Unavailable</span>) : <div className="skeleton" />}
        </Card>
        <Card title="Station queue" aside={data?.queue && <SourceBadge source={data.queue.source} />}>
          {data ? (data.queue ? <Stat label="Typical wait" value={data.queue.predicted_wait_min.toFixed(0)} unit="min" /> : <span className="empty">Unavailable</span>) : <div className="skeleton" />}
        </Card>
      </div>

      <div className="grid cols-3">
        <Card title="Smart charging">
          <div className="stack">
            <p style={{ color: "var(--text-secondary)" }}>Enter your battery level and conditions. The optimiser answers: charge now, or wait.</p>
            <Link className="btn" href="/smart-charging" style={{ alignSelf: "flex-start" }}>Get a recommendation</Link>
          </div>
        </Card>
        <Card title="Journey planner">
          <div className="stack">
            <p style={{ color: "var(--text-secondary)" }}>Check whether you can reach a destination on the current charge, and see stations on the way.</p>
            <Link className="btn ghost" href="/journey" style={{ alignSelf: "flex-start" }}>Plan a trip</Link>
          </div>
        </Card>
        <Card title="Policy simulator">
          <div className="stack">
            <p style={{ color: "var(--text-secondary)" }}>Compare the optimiser against simpler charging rules across a simulated fleet.</p>
            <Link className="btn ghost" href="/simulator" style={{ alignSelf: "flex-start" }}>Run a comparison</Link>
          </div>
        </Card>
      </div>
    </>
  );
}
