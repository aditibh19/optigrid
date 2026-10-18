"use client";
import dynamic from "next/dynamic";
import { useState } from "react";
import MapView, { type MapPoint } from "@/components/MapView";
import { Notice } from "@/components/ui";

// Leaflet touches `window`, so it must never render on the server.
const LeafletMap = dynamic(() => import("@/components/LeafletMap"), {
  ssr: false, loading: () => <div className="skeleton" style={{ height: 380 }} />,
});

/** Street map (Leaflet / OpenStreetMap) with a schematic fallback that works offline. */
export default function MapPanel({ points, route, ringKm, caption }: {
  points: MapPoint[]; route?: { lat: number; lng: number }[]; ringKm?: number; caption?: string;
}) {
  const [mode, setMode] = useState<"street" | "schematic">("street");
  const [tileProblem, setTileProblem] = useState(false);

  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="preset-row" role="tablist" aria-label="Map style">
        <button role="tab" aria-selected={mode === "street"} className="chip" onClick={() => setMode("street")}>Street map</button>
        <button role="tab" aria-selected={mode === "schematic"} className="chip" onClick={() => setMode("schematic")}>Schematic</button>
      </div>
      {mode === "street" && tileProblem && (
        <Notice tone="warn">Map tiles couldn&apos;t load, probably because you&apos;re offline. Switch to Schematic, which needs no internet.</Notice>
      )}
      {mode === "street"
        ? <LeafletMap points={points} route={route} ringKm={ringKm} onTileError={() => setTileProblem(true)} />
        : <MapView points={points} route={route} ringKm={ringKm} caption={caption} />}
      {mode === "street" && caption && <p className="hint" style={{ fontSize: 12, color: "var(--text-muted)" }}>{caption} Map data &copy; OpenStreetMap contributors.</p>}
    </div>
  );
}
