import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import Heatmap from "../charts/Heatmap";
import Histogram from "../charts/Histogram";
import LineChart from "../charts/LineChart";
import MetricBars from "../charts/MetricBars";
import { ramp, POWER_STOPS } from "../charts/color";
import MapView from "../components/MapView";

describe("colour ramp", () => {
  it("returns the end stops exactly", () => {
    expect(ramp(0, ["#000000", "#ffffff"])).toBe("rgb(0, 0, 0)");
    expect(ramp(1, ["#000000", "#ffffff"])).toBe("rgb(255, 255, 255)");
  });
  it("interpolates the midpoint and clamps out-of-range and NaN input", () => {
    expect(ramp(0.5, ["#000000", "#ffffff"])).toBe("rgb(128, 128, 128)");
    expect(ramp(-3, POWER_STOPS)).toBe(ramp(0, POWER_STOPS));
    expect(ramp(9, POWER_STOPS)).toBe(ramp(1, POWER_STOPS));
    expect(ramp(NaN, POWER_STOPS)).toBe(ramp(0, POWER_STOPS));
  });
});

describe("Heatmap", () => {
  const html = renderToStaticMarkup(
    <Heatmap matrix={[[0, 10], [20, 50]]} xLabels={["a", "b"]} yLabels={[0, 100]} min={0} max={50} stops={POWER_STOPS} xTitle="Time" yTitle="Battery" unit=" kW" showValues />);
  it("draws one cell per value, with tooltips and values", () => {
    expect((html.match(/<rect/g) ?? []).length).toBe(4);
    expect(html).toContain("Battery 100, Time b: 50 kW");
    expect(html).toContain(">50<");
  });
  it("labels both axes and the colour scale", () => {
    expect(html).toContain(">Time<");
    expect(html).toContain("0 kW");
    expect(html).toContain("50 kW");
  });
});

describe("LineChart", () => {
  it("renders every point of every series with a legend when there are several", () => {
    const html = renderToStaticMarkup(<LineChart xTitle="x" yTitle="y" series={[
      { name: "A", color: "red", points: [{ x: 1, y: 1 }, { x: 2, y: 3 }] }, { name: "B", color: "blue", points: [{ x: 1, y: 2 }, { x: 2, y: 2 }] }]} />);
    expect((html.match(/<circle/g) ?? []).length).toBe(4);
    expect(html).toContain("legend");
  });
  it("draws a step function with horizontal-then-vertical segments", () => {
    const html = renderToStaticMarkup(<LineChart xTitle="x" yTitle="y" series={[{ name: "S", color: "red", step: true, points: [{ x: 0, y: 1 }, { x: 1, y: 5 }] }]} />);
    expect(html).toMatch(/d="M[^"]*H[^"]*V/);
  });
  it("accepts category labels", () => {
    const html = renderToStaticMarkup(<LineChart xTitle="x" yTitle="y" series={[{ name: "S", color: "red", points: [{ x: "low", y: 1 }, { x: "high", y: 2 }] }]} />);
    expect(html).toContain(">low<");
  });
  it("says so when there is no data", () => {
    expect(renderToStaticMarkup(<LineChart xTitle="x" yTitle="y" series={[]} />)).toContain("No data");
  });
});

describe("Histogram", () => {
  it("draws one bar per bin per series", () => {
    const html = renderToStaticMarkup(<Histogram edges={[0, 1, 2, 3]} counts={{ a: [1, 2, 3], b: [3, 2, 1] }} colors={{ a: "red", b: "blue" }} labels={{ a: "A", b: "B" }} xTitle="cost" />);
    expect((html.match(/<rect/g) ?? []).length).toBe(6);
    expect(html).toContain("A: 3 runs between 2 and 3");
  });
});

describe("MetricBars", () => {
  it("highlights the best row and shows each mean", () => {
    const html = renderToStaticMarkup(<MetricBars rows={[{ label: "SDP", mean: 10, lo: 8, hi: 12, best: true }, { label: "Greedy", mean: 20, lo: 18, hi: 22, best: false }]} />);
    expect((html.match(/bar-fill best/g) ?? []).length).toBe(1);
    expect(html).toContain("10.00");
    expect(html).toContain("95% CI 18.00 to 22.00");
  });
});

describe("MapView (schematic)", () => {
  const html = renderToStaticMarkup(<MapView points={[
    { lat: 28.6, lng: 77.2, kind: "origin", label: "Delhi" }, { lat: 27.2, lng: 78.0, kind: "destination", label: "Agra" }]} route={[{ lat: 28.6, lng: 77.2 }, { lat: 27.2, lng: 78.0 }]} />);
  it("places points with north up and east right", () => {
    const [d, a] = [...html.matchAll(/translate\(([\d.]+) ([\d.]+)\)/g)].map((m) => [Number(m[1]), Number(m[2])]);
    expect(a[0]).toBeGreaterThan(d[0]);   // Agra is east of Delhi
    expect(a[1]).toBeGreaterThan(d[1]);   // Agra is south of Delhi (larger y = lower on screen)
  });
  it("draws the route and a scale bar", () => {
    expect(html).toContain("map-route");
    expect(html).toMatch(/\d+ km/);
  });
  it("draws a search-radius ring when asked", () => {
    expect(renderToStaticMarkup(<MapView points={[{ lat: 28.6, lng: 77.2, kind: "center" }]} ringKm={10} />)).toContain("map-ring");
  });
  it("handles having nothing to show", () => {
    expect(renderToStaticMarkup(<MapView points={[]} />)).toContain("Nothing to show");
  });
});
