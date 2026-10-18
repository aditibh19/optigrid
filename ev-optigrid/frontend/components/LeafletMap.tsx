"use client";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";
import type { MapPoint } from "@/components/MapView";

/** Street map (Leaflet + OpenStreetMap tiles). Loaded client-side only; see MapPanel. */
export default function LeafletMap({ points, route, ringKm, height = 380, onTileError }: {
  points: MapPoint[]; route?: { lat: number; lng: number }[]; ringKm?: number; height?: number; onTileError?: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const key = JSON.stringify({ points, route, ringKm });          // rebuild the map only when the data really changes
  const errorCb = useRef(onTileError);
  errorCb.current = onTileError;

  useEffect(() => {
    let map: import("leaflet").Map | undefined;
    let cancelled = false;
    (async () => {
      const L = (await import("leaflet")).default;
      if (cancelled || !host.current) return;
      map = L.map(host.current, { scrollWheelZoom: false, attributionControl: true });
      const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19, attribution: "&copy; OpenStreetMap contributors",
      }).addTo(map);
      tiles.on("tileerror", () => errorCb.current?.());

      const bounds = L.latLngBounds([]);
      points.forEach((p) => {
        const icon = L.divIcon({ className: "lf-icon", iconSize: [26, 26], iconAnchor: [13, 13],
          html: `<span class="lf-dot lf-${p.kind}">${p.badge ?? ""}</span>` });
        const marker = L.marker([p.lat, p.lng], { icon }).addTo(map!);
        const text = p.title ?? p.label;
        if (text) marker.bindTooltip(text, { direction: "top", offset: [0, -12] });
        bounds.extend([p.lat, p.lng]);
      });
      if (route && route.length > 1) {
        L.polyline(route.map((r) => [r.lat, r.lng] as [number, number]), { color: "#5B9BFF", weight: 3, dashArray: "8 8" }).addTo(map);
        route.forEach((r) => bounds.extend([r.lat, r.lng]));
      }
      if (ringKm && points[0]) {
        const ring = L.circle([points[0].lat, points[0].lng], { radius: ringKm * 1000, color: "#8B7BFA", weight: 1.5, dashArray: "5 5", fillOpacity: 0.05 }).addTo(map);
        bounds.extend(ring.getBounds());
      }
      if (bounds.isValid() && !bounds.getSouthWest().equals(bounds.getNorthEast())) map.fitBounds(bounds.pad(0.15));
      else if (points[0]) map.setView([points[0].lat, points[0].lng], 13);
    })();
    return () => { cancelled = true; map?.remove(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return <div ref={host} className="leaflet-wrap" style={{ height }} aria-label="Street map" />;
}
