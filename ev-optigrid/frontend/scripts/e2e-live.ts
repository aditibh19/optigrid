// Live end-to-end check: runs the REAL frontend service code (services/api.ts, services/auth.ts) against a
// running backend through the Next.js proxy. Start both servers first, then: npm run e2e
const BASE = process.env.FRONTEND_URL || "http://localhost:3000";
const realFetch = globalThis.fetch;
globalThis.fetch = ((u: any, i?: any) => realFetch(typeof u === "string" && u.startsWith("/") ? BASE + u : u, i)) as typeof fetch;

import * as api from "../services/api";
import { clearTokens, getTokens, saveTokens } from "../services/auth";

let pass = 0, fail = 0;
const ok = (name: string, cond: boolean, extra = "") => { (cond ? pass++ : fail++); console.log(`${cond ? "PASS" : "FAIL"}  ${name} ${extra}`); };
const rejects = async (p: Promise<unknown>) => p.then(() => null, (e) => e as api.ApiError);

const OPT: api.OptimizeRequest = { battery_capacity_kwh: 60, max_charge_rate_kw: 50, current_soc_pct: 32, target_soc_pct: 90, minimum_safe_soc_pct: 70,
  horizon_slots: 24, slot_minutes: 15, current_price_per_kwh: 8, current_grid_load_pct: 60, current_solar_availability_frac: 0.2, profile: "balanced" };
const POLICY: api.PolicyParams = { battery_capacity_kwh: 60, max_charge_rate_kw: 50, target_soc_pct: 90, minimum_safe_soc_pct: 70, horizon_slots: 8, slot_minutes: 15, profile: "balanced" };
const COND: api.Conditions = { current_soc_pct: 40, current_price_per_kwh: 8, current_grid_load_pct: 60, current_solar_availability_frac: 0.2 };

async function main() {
  // ── public endpoints work without logging in ──────────────────────────
  clearTokens();
  const [pr, gr, so, qu] = await Promise.all([api.predictPrice(), api.predictGrid(), api.predictSolar(), api.predictQueue()]);
  ok("public: forecasts", [pr, gr, so, qu].every((f) => f.source === "predicted"), `price=${pr.predicted_price_per_kwh}`);
  const stPublic = await api.nearbyStations({ lat: 28.6139, lng: 77.209, radius_km: 10, limit: 10, profile: "balanced", vehicle_max_charge_rate_kw: 50, target_soc_pct: 80, current_soc_pct: 30 });
  ok("public: stations ranked by score", stPublic.length > 0 && stPublic.every((s, i) => i === 0 || (stPublic[i - 1].cos_score ?? 0) >= (s.cos_score ?? 0)), `${stPublic.length} stations`);

  // ── protected endpoints refuse anonymous callers ──────────────────────
  const anon = await rejects(api.listVehicles());
  ok("anonymous -> 401 on a protected endpoint", anon?.status === 401, `"${anon?.message.slice(0, 50)}"`);

  // ── register, login, wrong password, /me ──────────────────────────────
  const email = `e2e-${Math.random().toString(36).slice(2, 9)}@evoptigrid.dev`;
  const password = "e2e-password-123";
  saveTokens(await api.register(email, password, "E2E Driver"));
  ok("register + me", (await api.fetchMe()).email === email);
  clearTokens();
  const bad = await rejects(api.login(email, "wrong-password"));
  ok("wrong password -> 401 with readable message", bad?.status === 401 && /password/i.test(bad.message), `"${bad?.message}"`);
  saveTokens(await api.login(email, password));
  ok("login again", (await api.fetchMe()).name === "E2E Driver");

  // ── silent token refresh: corrupt the access token, keep the refresh token ──
  const t = getTokens()!;
  saveTokens({ access_token: "expired.or.invalid", refresh_token: t.refresh_token });
  const me2 = await api.fetchMe();
  ok("expired access token is refreshed transparently", me2.email === email && getTokens()!.access_token !== "expired.or.invalid");

  // ── vehicles (owner-only) ──────────────────────────────────────────────
  const v = await api.createVehicle({ make: "Tata", model: "Nexon EV", battery_capacity_kwh: 40.5, efficiency_kwh_per_km: 0.16, max_charge_rate_kw: 50, current_soc: 32 });
  ok("create + list vehicle", (await api.listVehicles()).some((x) => x.id === v.id));

  // ── journey, route, copilot ───────────────────────────────────────────
  const [plan, route] = await Promise.all([
    api.planJourney({ origin_lat: 28.6139, origin_lng: 77.209, dest_lat: 27.1767, dest_lng: 78.0081, vehicle_id: v.id, target_soc_pct: 90 }),
    api.stationsAlongRoute({ origin_lat: 28.6139, origin_lng: 77.209, dest_lat: 27.1767, dest_lng: 78.0081 })]);
  ok("journey plan + route stations", !!plan.journey_id && plan.distance_km > 100 && route.stations.length > 0, `${plan.distance_km} km, ${route.stations.length} stations`);
  const cp = await api.copilotParse("I need to reach Agra by 6pm with 80% charge", v.id);
  ok("copilot uses the saved vehicle", cp.is_valid && cp.extracted_target_soc_pct === 80, `intent=${cp.intent}`);

  // ── smart charging + monitoring / re-optimisation ────────────────────
  const opt = await api.optimizeCharging(OPT);
  ok("optimize -> verdict, reasons, result id", !!opt.result_id && opt.reasons.length > 0, `action=${opt.recommended_action}`);
  for (const profile of ["save_money", "fastest", "battery_health", "green"] as const) {
    ok(`profile ${profile}`, typeof (await api.optimizeCharging({ ...OPT, profile })).recommended_action === "string");
  }
  const verr = await rejects(api.optimizeCharging({ ...OPT, current_soc_pct: 150 }));
  ok("validation error is readable", verr?.status === 422 && /current_soc_pct/.test(verr.message), `"${verr?.message}"`);
  const calm = await api.monitorConditions({ previous: OPT, current: { ...OPT, current_price_per_kwh: 8.5 } });
  ok("monitor: small change is ignored", !calm.changed && calm.triggers.length === 0);
  const spike = await api.monitorConditions({ previous: OPT, current: { ...OPT, current_price_per_kwh: 14, current_grid_load_pct: 85 }, previous_queue_wait_min: 5, current_queue_wait_min: 30 });
  ok("monitor: material change triggers a new plan", spike.changed && spike.triggers.length === 3 && !!spike.current.result_id,
     spike.triggers.map((x) => x.code).join(", "));

  // ── how the optimiser decides ─────────────────────────────────────────
  const space = await api.getStateSpace();
  ok("state space", space.counts.states_per_slot === 567 && space.counts.actions === 9);
  const soc = await api.getSocTransition({ soc_pct: 30, action_kw: 5, battery_capacity_kwh: 60, slot_minutes: 15 });
  ok("SOC interpolation is unbiased", Math.abs(soc.expected_bucket_soc_pct - soc.soc_after_continuous_pct) < 0.01);
  const hm = await api.getPolicyHeatmap({ ...POLICY, horizon_slots: 24, mode: "soc_by_time", vary: "price", t: 0, price_level: 1, grid_level: 1, solar_level: 1 });
  ok("policy heatmap 21 x 24", hm.action_kw.length === 21 && hm.action_kw[0].length === 24);
  const bell = await api.getBellman({ ...POLICY, t: 0, soc_pct: 40, price_level: 0, grid_level: 1, solar_level: 2 });
  ok("Bellman breakdown reproduces the solver", bell.matches_solver && bell.actions.every((a) => a.components_add_up), `best=${bell.best_action_kw} kW, residual ${bell.residual.toExponential(1)}`);
  const mc = await api.runMonteCarlo({ ...POLICY, ...COND, n_runs: 300, seed: 1 });
  ok("Monte Carlo: optimised is cheaper on paired scenarios", mc.paired_vs.charge_immediately.mean_saving_inr > 0 && mc.paired_vs.charge_immediately.ci95_low > 0,
     `saves ₹${mc.paired_vs.charge_immediately.mean_saving_inr.toFixed(0)}`);
  for (const sweep of ["soc", "price", "grid", "solar", "profile", "cost_weight"] as const) {
    ok(`sensitivity: ${sweep}`, (await api.runSensitivity({ ...POLICY, ...COND, sweep })).points.length >= 5);
  }

  // ── digital twin, fleet, battery ──────────────────────────────────────
  const twin = await api.runTwin({ ...POLICY, ...COND, horizon_slots: 16, seed: 7 });
  ok("digital twin: two lanes, 16 slots", twin.lanes.sdp.records.length === 16 && twin.lanes.charge_immediately.records.length === 16, `₹${twin.lanes.sdp.cost_inr.toFixed(0)} vs ₹${twin.lanes.charge_immediately.cost_inr.toFixed(0)}`);
  const fleet = await api.allocateFleet({ vehicles: [1, 2, 3, 4, 5].map((i) => ({ vehicle_id: i, name: `EV${i}`, current_soc_pct: 10 + 8 * i, target_soc_pct: 80, battery_capacity_kwh: 60, max_charge_rate_kw: 50, urgency: 1 + (i % 5), deadline_hours: 2 })),
    chargers: [{ charger_id: 1, power_kw: 50 }, { charger_id: 2, power_kw: 22 }], grid_capacity_kw: 60 });
  ok("fleet allocation respects every limit", fleet.constraint_violations.length === 0 && fleet.totals.grid_used_kw <= 60, `${fleet.service_score_pct.optimised}% vs ${fleet.service_score_pct.first_come_first_served}% first-come`);
  const bat = await api.getBatteryCurves({ max_charge_rate_kw: 50, ambient_temp_c: 25 });
  ok("battery curves", bat.by_charge_power.points.length > 10);

  // ── simulator (cost guard) ────────────────────────────────────────────
  const lim = await api.getSimulationLimits();
  const tooBig = await rejects(api.runSimulation({ num_evs: 25, num_chargers: 6, charger_power_kw: 50, grid_capacity_kw: 250, horizon_slots: 48, n_replications: 5, seed: 42 }));
  ok("simulator: oversized run refused instantly", tooBig?.status === 422 && /limit/i.test(tooBig.message), `limit ${lim.max_work}`);
  const t0 = Date.now();
  const sim = await api.runSimulation({ num_evs: 10, num_chargers: 4, charger_power_kw: 50, grid_capacity_kw: 150, horizon_slots: 24, n_replications: 2, seed: 42 });
  ok("simulator: default run, 5 policies", sim.results.length === 5, `${((Date.now() - t0) / 1000).toFixed(1)}s`);

  // ── sign out ──────────────────────────────────────────────────────────
  clearTokens();
  const after = await rejects(api.listVehicles());
  ok("after sign-out protected endpoints are closed again", after?.status === 401);

  // ── backend unreachable ───────────────────────────────────────────────
  globalThis.fetch = (() => { throw new TypeError("network"); }) as any;
  const off = await rejects(api.predictPrice());
  ok("offline -> helpful message", off?.status === 0 && /uvicorn/.test(off.message));

  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
}
main().catch((e) => { console.error("CRASH", e); process.exit(1); });
