import type { Conditions, PolicyParams } from "./api";

export const DEFAULT_POLICY: PolicyParams = {
  battery_capacity_kwh: 60, max_charge_rate_kw: 50, target_soc_pct: 90, minimum_safe_soc_pct: 70,
  horizon_slots: 24, slot_minutes: 15, profile: "balanced",
};

/** A shorter look-ahead makes the curves informative: with 6 hours to spare the optimiser can almost always wait. */
export const SHORT_POLICY: PolicyParams = { ...DEFAULT_POLICY, horizon_slots: 8 };

export const DEFAULT_CONDITIONS: Conditions = {
  current_soc_pct: 40, current_price_per_kwh: 8, current_grid_load_pct: 60, current_solar_availability_frac: 0.2,
};

export const LEVELS = ["low", "medium", "high"] as const;
export const SOLAR_LEVELS = ["none", "some", "high"] as const;

export const PROFILE_OPTIONS = [
  { value: "balanced", label: "Balanced" }, { value: "save_money", label: "Save money" },
  { value: "fastest", label: "Fastest" }, { value: "battery_health", label: "Protect battery health" },
  { value: "green", label: "Use more renewable energy" },
] as const;

export const POLICY_LABEL: Record<string, string> = {
  sdp: "Optimised (SDP)", charge_immediately: "Charge immediately", off_peak_only: "Off-peak only",
  greedy: "Greedy", fixed_schedule: "Fixed schedule", price_threshold: "Price threshold", priority: "Priority",
};
export const POLICY_COLOR: Record<string, string> = {
  sdp: "var(--current)", charge_immediately: "var(--gold)", off_peak_only: "var(--signal)",
};
