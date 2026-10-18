"use client";
import { useState } from "react";
import MapPanel from "@/components/MapPanel";
import { Card, NumberField, TextField, PageHead, Notice, SourceBadge, Stat, allFinite, errorMessage } from "@/components/ui";
import { DEFAULT_VEHICLE, useVehicles } from "@/hooks/useVehicles";
import { planJourney, stationsAlongRoute, type JourneyPlan, type RouteStations, type VehicleInput } from "@/services/api";

const PLACES = [
  { name: "Agra", lat: 27.1767, lng: 78.0081 },
  { name: "Jaipur", lat: 26.9124, lng: 75.7873 },
  { name: "Chandigarh", lat: 30.7333, lng: 76.7794 },
  { name: "Lucknow", lat: 26.8467, lng: 80.9462 },
];

const hoursMinutes = (min: number) => `${Math.floor(min / 60)} h ${Math.round(min % 60)} min`;

function VehicleForm({ onSave, onCancel }: { onSave: (v: VehicleInput) => Promise<void>; onCancel?: () => void }) {
  const [v, setV] = useState<VehicleInput>(DEFAULT_VEHICLE);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof VehicleInput>(k: K, x: VehicleInput[K]) => setV((s) => ({ ...s, [k]: x }));
  return (
    <div className="stack" style={{ maxWidth: 560 }}>
      <div className="two">
        <TextField label="Make" value={v.make} onChange={(x) => set("make", x)} />
        <TextField label="Model" value={v.model} onChange={(x) => set("model", x)} />
      </div>
      <div className="two">
        <NumberField label="Battery size" value={v.battery_capacity_kwh} onChange={(x) => set("battery_capacity_kwh", x)} min={1} suffix="kWh" />
        <NumberField label="Energy use" value={v.efficiency_kwh_per_km} onChange={(x) => set("efficiency_kwh_per_km", x)} min={0.01} step={0.01} suffix="kWh/km" />
      </div>
      <div className="two">
        <NumberField label="Max charging speed" value={v.max_charge_rate_kw} onChange={(x) => set("max_charge_rate_kw", x)} min={1} suffix="kW" />
        <NumberField label="Charge now" value={v.current_soc} onChange={(x) => set("current_soc", x)} min={0} max={100} suffix="%" />
      </div>
      {error && <Notice tone="error">{error}</Notice>}
      <div className="row">
        <button className="btn" disabled={busy || !allFinite(v) || !v.make || !v.model}
          onClick={async () => { setBusy(true); setError(null); try { await onSave(v); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }}>
          {busy ? "Saving" : "Save vehicle"}
        </button>
        {onCancel && <button className="btn ghost" onClick={onCancel}>Cancel</button>}
      </div>
    </div>
  );
}

export default function JourneyPage() {
  const { vehicles, selected, selectedId, select, add, error: vehiclesError } = useVehicles();
  const [addingVehicle, setAddingVehicle] = useState(false);
  const [trip, setTrip] = useState({ origin_lat: 28.6139, origin_lng: 77.209, dest_lat: 27.1767, dest_lng: 78.0081, target_soc_pct: 90 });
  const [plan, setPlan] = useState<JourneyPlan | null>(null);
  const [route, setRoute] = useState<RouteStations | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const setT = <K extends keyof typeof trip>(k: K, v: (typeof trip)[K]) => setTrip((s) => ({ ...s, [k]: v }));

  async function submit() {
    if (!selected) return;
    setBusy(true); setError(null);
    try {
      const [p, r] = await Promise.all([
        planJourney({ ...trip, vehicle_id: selected.id }),
        stationsAlongRoute({ origin_lat: trip.origin_lat, origin_lng: trip.origin_lng, dest_lat: trip.dest_lat, dest_lng: trip.dest_lng }),
      ]);
      setPlan(p); setRoute(r);
    } catch (e) { setPlan(null); setRoute(null); setError(errorMessage(e)); }
    finally { setBusy(false); }
  }

  return (
    <>
      <PageHead title="Journey planner">
        Check whether your car can make a trip on its current charge, and which stations are along the way.
      </PageHead>

      {vehicles === null ? <div className="skeleton" style={{ height: 120 }} /> : vehicles.length === 0 || addingVehicle ? (
        <Card title={vehicles.length === 0 ? "First, tell us about your car" : "Add a vehicle"}>
          {vehiclesError && <div style={{ marginBottom: 12 }}><Notice tone="error">{vehiclesError}</Notice></div>}
          <VehicleForm onSave={async (v) => { await add(v); setAddingVehicle(false); }} onCancel={vehicles.length ? () => setAddingVehicle(false) : undefined} />
        </Card>
      ) : (
        <div className="split">
          <div className="stack">
            <Card title="Vehicle" aside={<button className="btn ghost small" onClick={() => setAddingVehicle(true)}>Add another</button>}>
              <div className="stack">
                <div className="field">
                  <label htmlFor="vehicle-pick">Planning for</label>
                  <div className="input-wrap">
                    <select id="vehicle-pick" value={selectedId ?? ""} onChange={(e) => { select(e.target.value); setPlan(null); setRoute(null); }}>
                      {vehicles.map((v) => <option key={v.id} value={v.id}>{v.make} {v.model} ({v.battery_capacity_kwh} kWh)</option>)}
                    </select>
                  </div>
                </div>
                {selected && <p style={{ color: "var(--text-secondary)" }}>Starting at {selected.current_soc}% charge.</p>}
              </div>
            </Card>
            <Card title="Trip">
              <div className="stack">
                <div className="preset-row" aria-label="Destination presets">
                  {PLACES.map((p) => (
                    <button key={p.name} className="chip" onClick={() => { setT("dest_lat", p.lat); setT("dest_lng", p.lng); }}>To {p.name}</button>
                  ))}
                </div>
                <div className="two">
                  <NumberField label="From latitude" value={trip.origin_lat} onChange={(v) => setT("origin_lat", v)} step={0.0001} />
                  <NumberField label="From longitude" value={trip.origin_lng} onChange={(v) => setT("origin_lng", v)} step={0.0001} />
                  <NumberField label="To latitude" value={trip.dest_lat} onChange={(v) => setT("dest_lat", v)} step={0.0001} />
                  <NumberField label="To longitude" value={trip.dest_lng} onChange={(v) => setT("dest_lng", v)} step={0.0001} />
                </div>
                <NumberField label="Charge wanted on arrival" value={trip.target_soc_pct} onChange={(v) => setT("target_soc_pct", v)} min={0} max={100} suffix="%" />
                <button className="btn" onClick={submit} disabled={busy || !allFinite(trip)}>{busy ? "Planning" : "Plan trip"}</button>
              </div>
            </Card>
          </div>

          <div className="stack">
            {error && <Notice tone="error">{error}</Notice>}
            {!plan && !error && <Card><p className="empty">Pick a destination and plan the trip to see the energy needed.</p></Card>}
            {plan && (
              <>
                {plan.is_feasible_without_charging
                  ? <Notice tone="good">You can make this trip without stopping to charge.</Notice>
                  : <Notice tone="warn">
                      You&apos;ll need to charge on this trip. Without charging you&apos;d run out about {Math.abs(plan.expected_arrival_soc_pct).toFixed(0)}%
                      of the battery short of arriving with any charge left.
                    </Notice>}
                <Card title="Trip summary" aside={<SourceBadge source={plan.route_source} />}>
                  <div className="grid cols-2" style={{ rowGap: 22 }}>
                    <Stat label="Distance" value={plan.distance_km.toFixed(0)} unit="km" />
                    <Stat label="Driving time" value={hoursMinutes(plan.duration_min)} />
                    <Stat label="Energy needed" value={plan.energy_required_kwh.toFixed(1)} unit="kWh" />
                    <Stat label="Arrival charge without stopping" value={plan.expected_arrival_soc_pct.toFixed(0)} unit="%" tone={plan.is_feasible_without_charging ? "good" : "bad"} />
                  </div>
                </Card>
                {route && (
                  <Card title="Route map">
                    <MapPanel
                      route={[{ lat: trip.origin_lat, lng: trip.origin_lng }, { lat: trip.dest_lat, lng: trip.dest_lng }]}
                      points={[
                        { lat: trip.origin_lat, lng: trip.origin_lng, kind: "origin", label: "Start" },
                        { lat: trip.dest_lat, lng: trip.dest_lng, kind: "destination", label: "Destination" },
                        ...route.stations.map((s, i) => ({ lat: s.lat, lng: s.lng, kind: "station" as const, badge: String(i + 1), title: s.name })),
                      ]}
                      caption="Dashed line is the straight line between start and destination, not the road route. Numbered dots are charging stations."
                    />
                  </Card>
                )}
                {route && (
                  <Card title={`${route.stations.length} stations along the route`}>
                    {route.stations.length === 0 ? <p className="empty">No stations found near this route.</p> : (
                      <div className="table-wrap">
                        <table>
                          <thead><tr><th>#</th><th>Station</th><th className="num">Latitude</th><th className="num">Longitude</th><th>Data</th></tr></thead>
                          <tbody>
                            {route.stations.map((s, i) => (
                              <tr key={s.station_id}>
                                <td className="num">{i + 1}</td><td>{s.name}</td><td className="num">{s.lat.toFixed(3)}</td><td className="num">{s.lng.toFixed(3)}</td>
                                <td><SourceBadge source={s.source} /></td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </Card>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
