"use client";
import { useState } from "react";
import MapPanel from "@/components/MapPanel";
import { Card, NumberField, SelectField, PageHead, Notice, SourceBadge, allFinite, errorMessage, CURRENCY } from "@/components/ui";
import { nearbyStations, type Profile, type StationCard } from "@/services/api";

const PROFILES: { value: Profile; label: string }[] = [
  { value: "balanced", label: "Balanced" }, { value: "save_money", label: "Save money" },
  { value: "fastest", label: "Fastest" }, { value: "battery_health", label: "Protect battery health" },
  { value: "green", label: "Use more renewable energy" },
];

export default function StationsPage() {
  const [q, setQ] = useState({ lat: 28.6139, lng: 77.209, radius_km: 10, limit: 10, profile: "balanced" as Profile,
    vehicle_max_charge_rate_kw: 50, current_soc_pct: 30, target_soc_pct: 80 });
  const [stations, setStations] = useState<StationCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof typeof q>(k: K, v: (typeof q)[K]) => setQ((s) => ({ ...s, [k]: v }));

  async function search() {
    setBusy(true); setError(null);
    try { setStations(await nearbyStations(q)); }
    catch (e) { setStations(null); setError(errorMessage(e)); }
    finally { setBusy(false); }
  }

  const fastest = (s: StationCard) => Math.max(0, ...s.connectors.map((c) => c.power_kw));
  const cheapest = (s: StationCard) => (s.connectors.length ? Math.min(...s.connectors.map((c) => c.price_per_kwh)) : null);

  return (
    <>
      <PageHead title="Charging stations">
        Stations near a point, ranked by a Charging Opportunity Score that weighs distance, speed, price,
        expected queue and the effect on your battery.
      </PageHead>

      <Card>
        <div className="grid cols-4">
          <NumberField label="Latitude" value={q.lat} onChange={(v) => set("lat", v)} step={0.0001} />
          <NumberField label="Longitude" value={q.lng} onChange={(v) => set("lng", v)} step={0.0001} />
          <NumberField label="Search radius" value={q.radius_km} onChange={(v) => set("radius_km", v)} min={1} max={100} suffix="km" />
          <SelectField label="What matters most" value={q.profile} onChange={(v) => set("profile", v)} options={PROFILES} />
          <NumberField label="Charge now" value={q.current_soc_pct} onChange={(v) => set("current_soc_pct", v)} min={0} max={100} suffix="%" />
          <NumberField label="Charge wanted" value={q.target_soc_pct} onChange={(v) => set("target_soc_pct", v)} min={0} max={100} suffix="%" />
          <NumberField label="Car's max charging speed" value={q.vehicle_max_charge_rate_kw} onChange={(v) => set("vehicle_max_charge_rate_kw", v)} min={1} suffix="kW" />
          <div className="field" style={{ justifyContent: "flex-end" }}>
            <button className="btn" onClick={search} disabled={busy || !allFinite(q)}>{busy ? "Searching" : "Find stations"}</button>
          </div>
        </div>
      </Card>

      <div style={{ marginTop: 22 }} className="stack">
        {error && <Notice tone="error">{error}</Notice>}
        {stations && stations.length === 0 && <Notice>No stations within {q.radius_km} km. Try a wider radius.</Notice>}
        {stations && stations.length > 0 && (
          <Card title="Map">
            <MapPanel
              ringKm={q.radius_km}
              points={[
                { lat: q.lat, lng: q.lng, kind: "center", label: "Search point" },
                ...stations.map((s, i) => ({ lat: s.lat, lng: s.lng, kind: "station" as const, badge: String(i + 1), title: `${i + 1}. ${s.name}` })),
              ]}
              caption={`Numbers match the ranking below. The dashed ring is your ${q.radius_km} km search radius.`}
            />
          </Card>
        )}
        {stations && stations.length > 0 && (
          <Card title={`${stations.length} stations, best first`}>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th className="num">#</th><th>Station</th><th className="num">Distance</th><th className="num">Fastest</th>
                    <th className="num">From</th><th className="num">Expected wait</th><th>Score</th><th>Data</th>
                  </tr>
                </thead>
                <tbody>
                  {stations.map((s, i) => (
                    <tr key={s.station_id}>
                      <td className="num">{i + 1}</td>
                      <td>{s.name}</td>
                      <td className="num">{s.distance_km !== null ? `${s.distance_km.toFixed(1)} km` : "n/a"}</td>
                      <td className="num">{fastest(s)} kW</td>
                      <td className="num">{cheapest(s) !== null ? `${CURRENCY}${cheapest(s)!.toFixed(2)}` : "n/a"}</td>
                      <td className="num">{s.predicted_wait_min !== null ? `${s.predicted_wait_min.toFixed(0)} min` : "n/a"}</td>
                      <td>
                        {s.cos_score !== null ? (
                          <div className="score">
                            <div className="score-track"><div className="score-fill" style={{ width: `${Math.max(0, Math.min(100, s.cos_score))}%` }} /></div>
                            <span className="mono">{s.cos_score.toFixed(0)}</span>
                          </div>
                        ) : "n/a"}
                      </td>
                      <td><SourceBadge source={s.source} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </div>
    </>
  );
}
