/**
 * Typed client for the EV-OptiGrid FastAPI backend (see docs/API.md).
 * Every call goes to a relative /api/... URL that next.config.mjs proxies
 * to the backend, so the browser never needs CORS.
 */

import { clearTokens, getTokens, notifySessionExpired, saveTokens } from "./auth";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const AUTH_PATHS = ["/api/auth/login", "/api/auth/register", "/api/auth/refresh"];

let refreshInFlight: Promise<boolean> | null = null;

/** Swaps the refresh token for a new pair. Concurrent callers share one request. */
function refreshTokens(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const current = getTokens();
      if (!current) return false;
      try {
        const res = await fetch("/api/auth/refresh", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: current.refresh_token }),
        });
        if (!res.ok) return false;
        saveTokens((await res.json()) as Tokens);
        return true;
      } catch { return false; }
    })().finally(() => { refreshInFlight = null; });
  }
  return refreshInFlight;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const send = () => {
    const token = getTokens()?.access_token;
    return fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init?.headers ?? {}) },
    });
  };

  let res: Response;
  try {
    res = await send();
    // Expired access token: refresh once, then retry the original request.
    if (res.status === 401 && !AUTH_PATHS.includes(path) && getTokens()) {
      if (await refreshTokens()) res = await send();
      else { clearTokens(); notifySessionExpired(); }
    }
  } catch {
    throw new ApiError(0, "Can't reach the backend. Start it with: cd backend && uvicorn main:app --reload");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
      else if (Array.isArray(body?.detail)) {
        detail = body.detail.map((d: { loc?: string[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; ");
      }
    } catch { /* keep statusText */ }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

const qs = (params: Record<string, string | number | undefined>) =>
  "?" + Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");

// ── data-source labelling (spec §29): every number shows where it came from ──
export type DataSource = "real" | "simulated" | "predicted" | "demo";

// ── charging optimisation ────────────────────────────────────────────────
export type Profile = "save_money" | "fastest" | "battery_health" | "green" | "balanced";

export interface OptimizeRequest {
  battery_capacity_kwh: number;
  max_charge_rate_kw: number;
  current_soc_pct: number;
  target_soc_pct: number;
  minimum_safe_soc_pct: number;
  horizon_slots: number;
  slot_minutes: number;
  current_price_per_kwh: number;
  current_grid_load_pct: number;
  current_solar_availability_frac: number;
  profile: Profile;
}

export interface Reason {
  reason_code: string;
  reason_text: string;
  supporting_value: number | null;
}

export interface OptimizeResponse {
  result_id: string | null;
  recommended_action: string;
  action_kw: number;
  is_feasible: boolean;
  max_achievable_soc_pct: number;
  /** Cost of THIS slot's action only, not the whole charge. */
  estimated_cost: number;
  /** Cost of one slot at full power, for comparison. */
  immediate_cost: number;
  explanation_paragraph: string;
  reasons: Reason[];
}

export const optimizeCharging = (body: OptimizeRequest) =>
  request<OptimizeResponse>("/api/charging/optimize", { method: "POST", body: JSON.stringify(body) });

// ── forecasts ────────────────────────────────────────────────────────────
export interface PriceForecast { predicted_price_per_kwh: number; source: DataSource }
export interface GridForecast { predicted_grid_load_pct: number; source: DataSource }
export interface SolarForecast { predicted_generation_kwh: number; source: DataSource }
export interface QueueForecast { predicted_queue: number; predicted_wait_min: number; availability_probability: number; source: DataSource }

export const predictPrice = () => request<PriceForecast>("/api/predictions/prices");
export const predictGrid = () => request<GridForecast>("/api/predictions/grid");
export const predictSolar = () => request<SolarForecast>("/api/predictions/solar");
export const predictQueue = () => request<QueueForecast>("/api/predictions/queue");

// ── stations ─────────────────────────────────────────────────────────────
export interface Connector { connector_type: string; power_kw: number; price_per_kwh: number; status: string }
export interface StationCard {
  station_id: string;
  name: string;
  lat: number;
  lng: number;
  distance_km: number | null;
  connectors: Connector[];
  predicted_queue: number | null;
  predicted_wait_min: number | null;
  cos_score: number | null;
  source: DataSource;
}

export const nearbyStations = (p: {
  lat: number; lng: number; radius_km: number; limit: number; profile: Profile;
  vehicle_max_charge_rate_kw: number; target_soc_pct: number; current_soc_pct: number;
}) => request<StationCard[]>("/api/stations/nearby" + qs(p));

export interface RouteStation { station_id: string; name: string; lat: number; lng: number; source: DataSource }
export interface RouteStations {
  route: { distance_km: number; duration_min: number; source: DataSource };
  stations: RouteStation[];
}
export const stationsAlongRoute = (p: { origin_lat: number; origin_lng: number; dest_lat: number; dest_lng: number }) =>
  request<RouteStations>("/api/stations/route" + qs(p));

// ── auth / vehicles / journeys ───────────────────────────────────────────
export interface Tokens { access_token: string; refresh_token: string; token_type: string }
export interface UserInfo { id: string; email: string; name: string }
export const register = (email: string, password: string, name: string) =>
  request<Tokens>("/api/auth/register", { method: "POST", body: JSON.stringify({ email, password, name }) });
export const login = (email: string, password: string) =>
  request<Tokens>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
export const fetchMe = () => request<UserInfo>("/api/auth/me");

export interface VehicleInput {
  make: string; model: string; battery_capacity_kwh: number;
  efficiency_kwh_per_km: number; max_charge_rate_kw: number; current_soc: number;
}
export interface Vehicle extends VehicleInput { id: string; battery_health_pct: number }
export const createVehicle = (v: VehicleInput) =>
  request<Vehicle>("/api/vehicles", { method: "POST", body: JSON.stringify(v) });
export const listVehicles = () => request<Vehicle[]>("/api/vehicles");

export interface JourneyPlan {
  journey_id: string | null;
  distance_km: number;
  duration_min: number;
  energy_required_kwh: number;
  expected_arrival_soc_pct: number;
  minimum_safe_soc_pct: number;
  is_feasible_without_charging: boolean;
  route_source: DataSource;
}
export const planJourney = (body: {
  origin_lat: number; origin_lng: number; dest_lat: number; dest_lng: number; vehicle_id: string; target_soc_pct: number;
}) => request<JourneyPlan>("/api/journeys", { method: "POST", body: JSON.stringify(body) });

// ── copilot ──────────────────────────────────────────────────────────────
export interface CopilotReply {
  intent: string;
  is_valid: boolean;
  validation_errors: string[];
  extracted_target_soc_pct: number | null;
  extracted_deadline: string | null;
  optimizer_result: Record<string, unknown> | null;
  reply_text: string;
}
export const copilotParse = (message: string, vehicleId?: string) =>
  request<CopilotReply>("/api/copilot/parse", { method: "POST", body: JSON.stringify({ message, vehicle_id: vehicleId ?? null }) });

// ── simulation ───────────────────────────────────────────────────────────
export interface MetricSummary { mean: number; std: number; ci95_low: number; ci95_high: number }
export interface AlgorithmResult { algorithm: string; n_replications: number; metrics: Record<string, MetricSummary> }
export interface SimulationRun { experiment_id: string; results: AlgorithmResult[] }
export interface SimulationParams {
  num_evs: number; num_chargers: number; charger_power_kw: number; grid_capacity_kw: number;
  horizon_slots: number; n_replications: number; seed: number;
}
export const runSimulation = (p: SimulationParams) =>
  request<SimulationRun>("/api/simulation/run", { method: "POST", body: JSON.stringify(p) });

export interface SimulationLimits { max_work: number; solves_per_second_cold: number; work_formula: string }
export const getSimulationLimits = () => request<SimulationLimits>("/api/simulation/limits");

// ── how the optimiser decides (analysis endpoints; all require login) ─────
export interface PolicyParams {
  battery_capacity_kwh: number; max_charge_rate_kw: number; target_soc_pct: number;
  minimum_safe_soc_pct: number; horizon_slots: number; slot_minutes: number; profile: Profile;
}
export interface Conditions {
  current_soc_pct: number; current_price_per_kwh: number; current_grid_load_pct: number; current_solar_availability_frac: number;
}

export interface StateSpace {
  soc_buckets: number[]; soc_step_pct: number;
  price: { levels: string[]; values_inr_per_kwh: number[]; thresholds: number[] };
  grid: { levels: string[]; values_load_pct: number[]; thresholds: number[] };
  solar: { levels: string[]; values_fraction: number[]; thresholds: number[] };
  actions_kw: number[];
  counts: { soc: number; price: number; grid: number; solar: number; exogenous_states: number; states_per_slot: number; actions: number; state_action_pairs_per_slot: number };
  transition_matrices: { price: number[][]; grid: number[][]; solar: number[][] };
  gamma: number; notes: string[];
}
export interface SocTransition {
  soc_before_pct: number; gain_pct: number; soc_after_continuous_pct: number;
  distribution: { probability: number; bucket_index: number; bucket_soc_pct: number }[];
  expected_bucket_soc_pct: number; nearest_bucket_soc_pct: number; start_bucket_soc_pct: number;
}
export const getStateSpace = () => request<StateSpace>("/api/analysis/state-space");
export const getSocTransition = (p: { soc_pct: number; action_kw: number; battery_capacity_kwh: number; slot_minutes: number }) =>
  request<SocTransition>("/api/analysis/soc-transition" + qs(p));

export interface Heatmap {
  mode: string; x_label: string; x_values: (number | string)[]; y_label: string; y_values: number[];
  action_kw: number[][]; value: number[][]; max_action_kw: number; cached: boolean;
  fixed: { price_level: string; grid_level: string; solar_level: string; t: number | null };
}
export interface HeatmapRequest extends PolicyParams {
  mode: "soc_by_time" | "soc_by_level"; vary: "price" | "grid" | "solar"; t: number;
  price_level: number; grid_level: number; solar_level: number;
}
export const getPolicyHeatmap = (b: HeatmapRequest) => request<Heatmap>("/api/analysis/policy-heatmap", { method: "POST", body: JSON.stringify(b) });

export interface BellmanAction {
  action_kw: number; soc_after_pct: number; delivered_kw: number;
  immediate_cost: { electricity: number; degradation: number; grid: number; renewable: number; total: number };
  components_add_up: boolean; expected_future_value: number; discounted_future_value: number; q_value: number;
  real_cost_inr: number; is_best: boolean; next_soc_distribution: { probability: number; soc_pct: number }[];
}
export interface Bellman {
  t: number; state: { soc_pct: number; price_level: string; grid_level: string; solar_level: string };
  gamma: number; next_is_terminal: boolean; actions: BellmanAction[]; best_action_kw: number; min_q: number;
  solver_value_function: number; residual: number; solver_policy_action_kw: number; matches_solver: boolean;
}
export interface BellmanRequest extends PolicyParams { t: number; soc_pct: number; price_level: number; grid_level: number; solar_level: number }
export const getBellman = (b: BellmanRequest) => request<Bellman>("/api/analysis/bellman", { method: "POST", body: JSON.stringify(b) });

export interface Summary { mean: number; std: number; p05: number; p50: number; p95: number; min: number; max: number }
export interface McPolicy {
  cost_inr: Summary; final_soc_pct: Summary; degradation: Summary; energy_kwh: Summary;
  target_met_pct: number; safe_soc_met_pct: number; grid_load_when_charging_pct: number | null;
}
export interface Histogram { edges: number[]; counts: Record<string, number[]> }
export interface Paired { mean_saving_inr: number; ci95_low: number; ci95_high: number; sdp_cheaper_pct: number; sdp_cheaper_or_equal_pct: number }
export interface MonteCarlo {
  n_runs: number; seed: number; start: { price_level: string; grid_level: string; solar_level: string };
  policies: Record<string, McPolicy>; histograms: { cost_inr: Histogram; final_soc_pct: Histogram };
  paired_vs: Record<string, Paired>; note: string;
}
export interface MonteCarloRequest extends PolicyParams, Conditions { n_runs: number; seed: number }
export const runMonteCarlo = (b: MonteCarloRequest) => request<MonteCarlo>("/api/analysis/monte-carlo", { method: "POST", body: JSON.stringify(b) });

export type SweepName = "soc" | "price" | "grid" | "solar" | "profile" | "cost_weight";
export interface SensitivityPoint { x: number | string; label: string; level: string; action_kw: number; value: number }
export interface Sensitivity {
  sweep: SweepName; x_label: string; points: SensitivityPoint[]; note: string;
  held_fixed: { soc_pct: number; price_level: string; grid_level: string; solar_level: string; profile: string };
}
export interface SensitivityRequest extends PolicyParams, Conditions { sweep: SweepName }
export const runSensitivity = (b: SensitivityRequest) => request<Sensitivity>("/api/analysis/sensitivity", { method: "POST", body: JSON.stringify(b) });

// ── digital twin ─────────────────────────────────────────────────────────
export interface TwinRecord {
  t: number; clock_min: number; soc_before_pct: number; soc_after_pct: number; action_kw: number; delivered_kw: number;
  price_level: string; price_inr_per_kwh: number; grid_level: string; grid_load_pct: number;
  solar_level: string; solar_fraction: number; slot_cost_inr: number; cumulative_cost_inr: number;
  cumulative_energy_kwh: number; degradation: number;
}
export interface TwinLane { cost_inr: number; final_soc_pct: number; degradation: number; energy_kwh: number; records: TwinRecord[] }
export interface Twin {
  config: { battery_capacity_kwh: number; max_charge_rate_kw: number; slot_minutes: number; horizon_slots: number;
            target_soc_pct: number; minimum_safe_soc_pct: number; start_soc_pct: number; profile: string; seed: number };
  lanes: { sdp: TwinLane; charge_immediately: TwinLane }; note: string;
}
export interface TwinRequest extends PolicyParams, Conditions { seed: number }
export const runTwin = (b: TwinRequest) => request<Twin>("/api/twin/run", { method: "POST", body: JSON.stringify(b) });

// ── fleet ────────────────────────────────────────────────────────────────
export interface FleetVehicle {
  vehicle_id: number; name: string; current_soc_pct: number; target_soc_pct: number;
  battery_capacity_kwh: number; max_charge_rate_kw: number; urgency: number; deadline_hours: number;
}
export interface FleetCharger { charger_id: number; power_kw: number }
export interface FleetRequest { vehicles: FleetVehicle[]; chargers: FleetCharger[]; grid_capacity_kw: number; charging_efficiency?: number }
export interface FleetVehicleResult {
  vehicle_id: number; name: string; urgency: number; needs_kwh: number; desired_kw: number; allocated_kw: number;
  charger_id: number | null; status: "charging" | "partial" | "waiting" | "at_target"; reason: string; minutes_to_target: number | null;
}
export interface FleetResult {
  vehicles: FleetVehicleResult[];
  chargers: { charger_id: number; power_kw: number; allocated_kw: number; vehicle_ids: number[] }[];
  totals: { grid_capacity_kw: number; grid_used_kw: number; grid_utilisation_pct: number; vehicles_charging: number; vehicles_waiting: number };
  constraint_violations: string[]; service_score_pct: { optimised: number; first_come_first_served: number };
  grid_used_kw_first_come: number; note: string;
}
export const allocateFleet = (b: FleetRequest) => request<FleetResult>("/api/fleet/allocate", { method: "POST", body: JSON.stringify(b) });

// ── battery ──────────────────────────────────────────────────────────────
export interface WearPoint { x: number; total: number; components: { depth_of_discharge: number; high_soc_exposure: number; charge_rate: number; temperature: number } }
export interface BatteryCurves {
  weights: Record<string, number>; max_charge_rate_kw: number; ambient_temp_c: number | null;
  by_charge_power: { x_label: string; window: string; points: WearPoint[] };
  by_end_soc: { x_label: string; window: string; points: WearPoint[] };
  by_temperature: { x_label: string; window: string; points: WearPoint[] };
  health_indicator: { x_label: string; points: { x: number; health_pct: number }[] }; note: string;
}
export const getBatteryCurves = (p: { max_charge_rate_kw: number; ambient_temp_c: number }) => request<BatteryCurves>("/api/battery/curves" + qs(p));

// ── monitoring and re-optimisation ───────────────────────────────────────
export interface MonitorTrigger { code: string; label: string; previous: number; current: number; threshold: number; unit: string }
export interface MonitorResult {
  changed: boolean; triggers: MonitorTrigger[]; thresholds: Record<string, number>;
  action_changed: boolean; reoptimized: boolean; stored: boolean; previous: OptimizeResponse; current: OptimizeResponse;
}
export const monitorConditions = (b: {
  previous: OptimizeRequest; current: OptimizeRequest; previous_queue_wait_min?: number; current_queue_wait_min?: number; journey_id?: string;
}) => request<MonitorResult>("/api/charging/monitor", { method: "POST", body: JSON.stringify(b) });
