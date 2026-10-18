/**
 * Schematic map: true relative positions on an equirectangular projection, with a
 * graticule and scale bar. It deliberately does NOT pretend to be a road map — there are
 * no map tiles, so routes are drawn as straight lines between their end points.
 */
export interface MapPoint {
  lat: number; lng: number;
  kind: "origin" | "destination" | "station" | "center";
  label?: string;      // shown next to the marker
  badge?: string;      // short text inside the marker (e.g. a rank)
  title?: string;      // tooltip
}

const KM_PER_DEG = 111.32;
const W = 760;

const COLOR: Record<MapPoint["kind"], string> = {
  origin: "var(--renewable)", destination: "var(--gold)", station: "var(--signal)", center: "var(--current)",
};

function niceStep(span: number): number {
  const target = span / 5;
  return [0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10].find((s) => s >= target) ?? 10;
}

export default function MapView({ points, route, ringKm, height = 380, caption }: {
  points: MapPoint[]; route?: { lat: number; lng: number }[]; ringKm?: number; height?: number; caption?: string;
}) {
  const all = [...points, ...(route ?? [])];
  if (all.length === 0) return <div className="empty">Nothing to show on the map yet.</div>;

  let minLat = Math.min(...all.map((p) => p.lat)), maxLat = Math.max(...all.map((p) => p.lat));
  let minLng = Math.min(...all.map((p) => p.lng)), maxLng = Math.max(...all.map((p) => p.lng));
  if (ringKm && points[0]) {
    const dLat = ringKm / KM_PER_DEG, dLng = ringKm / (KM_PER_DEG * Math.cos((points[0].lat * Math.PI) / 180));
    minLat = Math.min(minLat, points[0].lat - dLat); maxLat = Math.max(maxLat, points[0].lat + dLat);
    minLng = Math.min(minLng, points[0].lng - dLng); maxLng = Math.max(maxLng, points[0].lng + dLng);
  }
  const midLat = (minLat + maxLat) / 2;
  const kx = Math.cos((midLat * Math.PI) / 180);
  const spanX = Math.max((maxLng - minLng) * kx, 0.02), spanY = Math.max(maxLat - minLat, 0.02);
  const pad = 46;
  const scale = Math.min((W - 2 * pad) / spanX, (height - 2 * pad) / spanY);   // px per degree of latitude
  const offX = (W - spanX * scale) / 2, offY = (height - spanY * scale) / 2;
  const px = (lng: number) => offX + (lng - minLng) * kx * scale;
  const py = (lat: number) => offY + (maxLat - lat) * scale;

  const step = niceStep(Math.max(spanX, spanY));
  const lats: number[] = [], lngs: number[] = [];
  for (let v = Math.ceil(minLat / step) * step; v <= maxLat + 1e-9; v += step) lats.push(+v.toFixed(4));
  for (let v = Math.ceil(minLng / step) * step; v <= maxLng + 1e-9; v += step) lngs.push(+v.toFixed(4));

  const barKm = [1, 2, 5, 10, 20, 50, 100, 200, 500].find((k) => (k / KM_PER_DEG) * scale >= 60) ?? 500;
  const barPx = (barKm / KM_PER_DEG) * scale;
  const center = points[0];

  return (
    <figure className="map">
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={caption ?? "Schematic map"}>
        <rect x="0" y="0" width={W} height={height} rx="14" className="map-bg" />
        {lats.map((v) => <g key={`la${v}`}><line x1="0" x2={W} y1={py(v)} y2={py(v)} className="map-grid" /><text x="8" y={py(v) - 4} className="map-tick">{v}°N</text></g>)}
        {lngs.map((v) => <g key={`ln${v}`}><line y1="0" y2={height} x1={px(v)} x2={px(v)} className="map-grid" /><text y={height - 8} x={px(v) + 4} className="map-tick">{v}°E</text></g>)}

        {ringKm && center && <circle cx={px(center.lng)} cy={py(center.lat)} r={(ringKm / KM_PER_DEG) * scale} className="map-ring" />}
        {route && route.length > 1 && <polyline points={route.map((p) => `${px(p.lng)},${py(p.lat)}`).join(" ")} className="map-route" />}

        {points.map((p, i) => (
          <g key={i} transform={`translate(${px(p.lng)} ${py(p.lat)})`}>
            <title>{p.title ?? p.label ?? p.kind}</title>
            <circle r={p.badge ? 11 : 8} style={{ fill: COLOR[p.kind] }} className="map-dot" />
            {p.badge && <text className="map-badge" textAnchor="middle" dy="0.35em">{p.badge}</text>}
            {p.label && <text x="15" y="4" className="map-label">{p.label}</text>}
          </g>
        ))}

        <g transform={`translate(${W - barPx - 22} ${height - 26})`}>
          <line x1="0" x2={barPx} y1="0" y2="0" className="map-scale" />
          <line x1="0" x2="0" y1="-4" y2="4" className="map-scale" /><line x1={barPx} x2={barPx} y1="-4" y2="4" className="map-scale" />
          <text x={barPx / 2} y="-8" textAnchor="middle" className="map-tick">{barKm} km</text>
        </g>
      </svg>
      <figcaption>{caption ?? "Schematic map: positions are to scale, but there are no map tiles or roads."}</figcaption>
    </figure>
  );
}
