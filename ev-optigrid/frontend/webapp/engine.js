/**
 * EV-OptiGrid — Client-side decision engine.
 *
 * Faithful port of the Python algorithms in /optimization and /ml, so this
 * standalone frontend demo computes REAL results (spec §42: "do not create
 * a fake UI around fake calculations") without requiring the FastAPI
 * backend to be running. A production deployment calls the actual Python
 * backend instead (see backend/api/*.py) — this port exists so the project
 * is fully demonstrable by opening one HTML file, no server needed.
 */
const Engine = (() => {
  "use strict";

  // ---- MDP discretization (mirrors optimization/mdp.py) ----
  const SOC_STEP = 5.0;
  const N_SOC = Math.round(100 / SOC_STEP) + 1; // 21
  const PRICE_LEVELS = ["low", "medium", "high"];
  const GRID_LEVELS = ["low", "medium", "high"];
  const SOLAR_LEVELS = ["none", "some", "high"];
  const N_PRICE = 3, N_GRID = 3, N_SOLAR = 3;
  const DEFAULT_ACTIONS_KW = [0, 5, 10, 15, 20, 25, 30, 40, 50];
  const GLOBAL_REFERENCE_MAX_KW = Math.max(...DEFAULT_ACTIONS_KW);

  function socFromBucket(idx) { return idx * SOC_STEP; }
  function nearestSocBucket(pct) {
    return Math.max(0, Math.min(N_SOC - 1, Math.round(pct / SOC_STEP)));
  }

  function socTransitionDistribution(socBeforePct, gainPct) {
    const socAfter = Math.max(0, Math.min(100, socBeforePct + gainPct));
    const exact = socAfter / SOC_STEP;
    let lo = Math.floor(exact), hi = Math.ceil(exact);
    lo = Math.max(0, Math.min(N_SOC - 1, lo));
    hi = Math.max(0, Math.min(N_SOC - 1, hi));
    if (lo === hi) return [[1.0, lo]];
    const fracHigh = exact - lo, fracLow = 1 - fracHigh;
    return [[fracLow, lo], [fracHigh, hi]];
  }

  function bucketize(value, tLow, tHigh) {
    if (value <= tLow) return 0;
    if (value >= tHigh) return 2;
    return 1;
  }
  const bucketizePrice = (v) => bucketize(v, 6.0, 11.0);
  const bucketizeGrid = (v) => bucketize(v, 50.0, 80.0);
  const bucketizeSolar = (v) => bucketize(v, 0.05, 0.6);

  class MDPConfig {
    constructor(opts) {
      this.batteryCapacityKwh = opts.batteryCapacityKwh;
      this.maxChargeRateKw = opts.maxChargeRateKw;
      this.chargingEfficiency = opts.chargingEfficiency != null ? opts.chargingEfficiency : 0.9;
      this.slotMinutes = opts.slotMinutes || 15;
      this.horizonSlots = opts.horizonSlots || 24;
      this.actionsKw = opts.actionsKw || DEFAULT_ACTIONS_KW;
    }
    get slotHours() { return this.slotMinutes / 60.0; }
    feasibleActionsKw() {
      const feasible = this.actionsKw.filter((a) => a <= this.maxChargeRateKw + 1e-9);
      return feasible.length ? feasible : [0.0];
    }
    socGainPct(actionKw) {
      const energyKwh = actionKw * this.slotHours * this.chargingEfficiency;
      return (energyKwh / this.batteryCapacityKwh) * 100.0;
    }
  }

  // ---- Transition model (mirrors optimization/transition_model.py) ----
  function buildDefaultTransitionMatrix(n, persistence) {
    if (persistence === undefined) persistence = 0.7;
    const m = [];
    for (let i = 0; i < n; i++) m.push(new Array(n).fill(0));
    for (let i = 0; i < n; i++) {
      m[i][i] = persistence;
      const remaining = 1 - persistence;
      const neighbors = [i - 1, i + 1].filter((j) => j >= 0 && j < n);
      if (neighbors.length) neighbors.forEach((j) => (m[i][j] = remaining / neighbors.length));
      else m[i][i] = 1.0;
    }
    return m;
  }

  function TransitionModel() {
    this.price = buildDefaultTransitionMatrix(N_PRICE, 0.7);
    this.grid = buildDefaultTransitionMatrix(N_GRID, 0.7);
    this.solar = buildDefaultTransitionMatrix(N_SOLAR, 0.6);
  }

  function jointTransitionTensor(tm) {
    const T = [];
    for (let p = 0; p < N_PRICE; p++) {
      T.push([]);
      for (let g = 0; g < N_GRID; g++) {
        T[p].push([]);
        for (let s = 0; s < N_SOLAR; s++) {
          const slice = [];
          for (let i = 0; i < N_PRICE; i++) {
            const row2 = [];
            for (let j = 0; j < N_GRID; j++) {
              const row = [];
              for (let k = 0; k < N_SOLAR; k++) row.push(tm.price[p][i] * tm.grid[g][j] * tm.solar[s][k]);
              row2.push(row);
            }
            slice.push(row2);
          }
          T[p][g].push(slice);
        }
      }
    }
    return T;
  }

  // ---- Reward model (mirrors optimization/reward_model.py) ----
  const DEFAULT_PRICE_VALUES = { 0: 4.5, 1: 8.0, 2: 13.5 };
  const DEFAULT_GRID_LOAD_VALUES = { 0: 35.0, 1: 65.0, 2: 90.0 };
  const DEFAULT_SOLAR_AVAIL_VALUES = { 0: 0.0, 1: 0.4, 2: 1.0 };
  const WORST_CASE_PRICE = Math.max.apply(null, Object.keys(DEFAULT_PRICE_VALUES).map((k) => DEFAULT_PRICE_VALUES[k]));

  const PROFILE_WEIGHTS = {
    save_money: { wCost: 3.0, wBattery: 0.5, wGrid: 0.3, wUnmet: 5.0, wDeadline: 4.0, wRenewable: 0.3 },
    fastest: { wCost: 0.3, wBattery: 0.2, wGrid: 0.1, wUnmet: 5.0, wDeadline: 6.0, wRenewable: 0.1 },
    battery_health: { wCost: 0.5, wBattery: 3.0, wGrid: 0.3, wUnmet: 5.0, wDeadline: 4.0, wRenewable: 0.3 },
    green: { wCost: 0.5, wBattery: 0.5, wGrid: 0.5, wUnmet: 5.0, wDeadline: 4.0, wRenewable: 3.0 },
    balanced: { wCost: 1.0, wBattery: 1.0, wGrid: 1.0, wUnmet: 5.0, wDeadline: 4.0, wRenewable: 1.0 },
    custom: { wCost: 1.0, wBattery: 1.0, wGrid: 1.0, wUnmet: 5.0, wDeadline: 4.0, wRenewable: 1.0 },
  };
  function resolveWeights(profile, overrides) {
    const base = PROFILE_WEIGHTS[profile] || PROFILE_WEIGHTS.balanced;
    if (profile !== "custom" || !overrides) return base;
    return Object.assign({}, base, overrides);
  }

  const BATTERY_WEIGHTS = { kDod: 0.3, kHighSoc: 0.25, kChargeRate: 0.35, kTemperature: 0.1 };
  function depthOfDischargeTerm(before, after) { return Math.pow(Math.abs(after - before) / 100.0, 1.2); }
  function highSocExposureTerm(after, threshold) {
    if (threshold === undefined) threshold = 80.0;
    if (after <= threshold) return 0.0;
    return (after - threshold) / (100.0 - threshold);
  }
  function highChargingPowerTerm(kw, maxKw) {
    if (maxKw <= 0) return 0.0;
    return Math.pow(Math.min(1.0, kw / maxKw), 1.5);
  }
  function computeDegradationCost(socBefore, socAfter, chargeKw, maxChargeKw) {
    const dod = depthOfDischargeTerm(socBefore, socAfter);
    const highSoc = highSocExposureTerm(socAfter);
    const rate = highChargingPowerTerm(chargeKw, maxChargeKw);
    return BATTERY_WEIGHTS.kDod * dod + BATTERY_WEIGHTS.kHighSoc * highSoc + BATTERY_WEIGHTS.kChargeRate * rate;
  }
  function batteryHealthIndicator(cumulativeCost, scale) {
    if (scale === undefined) scale = 500.0;
    return Math.round(100 * Math.max(0, 1 - cumulativeCost / scale) * 100) / 100;
  }

  function stepCost(socBeforePct, socAfterPct, actionKw, maxChargeRateKw, priceIdx, gridIdx, solarIdx, slotHours, w) {
    const pricePerKwh = DEFAULT_PRICE_VALUES[priceIdx];
    const gridLoadFrac = DEFAULT_GRID_LOAD_VALUES[gridIdx] / 100.0;
    const solarAvailFrac = DEFAULT_SOLAR_AVAIL_VALUES[solarIdx];

    const energyKwh = actionKw * slotHours;
    const rawCost = energyKwh * pricePerKwh;
    const worstCaseCost = GLOBAL_REFERENCE_MAX_KW * slotHours * WORST_CASE_PRICE;
    const electricityCost = rawCost / worstCaseCost;

    const degradationCost = computeDegradationCost(socBeforePct, socAfterPct, actionKw, maxChargeRateKw);
    const gridPenalty = Math.pow(gridLoadFrac, 2) * (actionKw / GLOBAL_REFERENCE_MAX_KW);
    const renewableReward = solarAvailFrac * (actionKw / GLOBAL_REFERENCE_MAX_KW);

    return w.wCost * electricityCost + w.wBattery * degradationCost + w.wGrid * gridPenalty - w.wRenewable * renewableReward;
  }

  function terminalCost(finalSocPct, targetSocPct, minSafeSocPct, w) {
    const unmet = Math.max(0, targetSocPct - finalSocPct);
    const unmetPenalty = w.wUnmet * (unmet / 100.0);
    const deadlineViolation = Math.max(0, minSafeSocPct - finalSocPct);
    const deadlinePenalty = w.wDeadline * (deadlineViolation / 100.0) * 5.0;
    return unmetPenalty + deadlinePenalty;
  }

  function realElectricityCost(actionKw, priceIdx, slotHours) {
    return actionKw * slotHours * DEFAULT_PRICE_VALUES[priceIdx];
  }

  // ---- Value iteration (mirrors optimization/value_iteration.py) ----
  function solveValueIteration(config, weights, targetSocPct, minSafeSocPct, tm, gamma) {
    tm = tm || new TransitionModel();
    if (gamma === undefined) gamma = 0.99;
    const T = jointTransitionTensor(tm);
    const actions = config.feasibleActionsKw();
    const horizon = config.horizonSlots;

    function zeros5(a, b, c, d) {
      const arr = [];
      for (let i = 0; i < a; i++) {
        const bi = [];
        for (let j = 0; j < b; j++) {
          const cj = [];
          for (let k = 0; k < c; k++) cj.push(new Array(d).fill(0));
          bi.push(cj);
        }
        arr.push(bi);
      }
      return arr;
    }

    const V = [];
    for (let t = 0; t <= horizon; t++) V.push(zeros5(N_SOC, N_PRICE, N_GRID, N_SOLAR));
    const policy = [];
    for (let t = 0; t < horizon; t++) policy.push(zeros5(N_SOC, N_PRICE, N_GRID, N_SOLAR));

    for (let socIdx = 0; socIdx < N_SOC; socIdx++) {
      const tc = terminalCost(socFromBucket(socIdx), targetSocPct, minSafeSocPct, weights);
      for (let p = 0; p < N_PRICE; p++)
        for (let g = 0; g < N_GRID; g++)
          for (let s = 0; s < N_SOLAR; s++) V[horizon][socIdx][p][g][s] = tc;
    }

    for (let t = horizon - 1; t >= 0; t--) {
      const Vnext = V[t + 1];
      for (let socIdx = 0; socIdx < N_SOC; socIdx++) {
        const socPct = socFromBucket(socIdx);
        let best = null;
        let bestAction = zeros5(1, N_PRICE, N_GRID, N_SOLAR)[0];

        actions.forEach((aKw, aIdx) => {
          const gainPct = config.socGainPct(aKw);
          const socAfterPct = Math.max(0, Math.min(100, socPct + gainPct));
          const socDist = socTransitionDistribution(socPct, gainPct);

          const actualGain = socAfterPct - socPct;
          let effectiveKw = 0;
          if (config.slotHours > 0 && config.chargingEfficiency > 0) {
            effectiveKw = ((actualGain / 100.0) * config.batteryCapacityKwh) / (config.chargingEfficiency * config.slotHours);
          }
          effectiveKw = Math.max(0, Math.min(aKw, effectiveKw));

          const total = zeros5(1, N_PRICE, N_GRID, N_SOLAR)[0];
          for (let p = 0; p < N_PRICE; p++) {
            for (let g = 0; g < N_GRID; g++) {
              for (let s = 0; s < N_SOLAR; s++) {
                const cost = stepCost(socPct, socAfterPct, effectiveKw, config.maxChargeRateKw, p, g, s, config.slotHours, weights);
                let expFuture = 0;
                for (const pair of socDist) {
                  const prob = pair[0], socAfterIdx = pair[1];
                  const vSlice = Vnext[socAfterIdx];
                  let acc = 0;
                  for (let i = 0; i < N_PRICE; i++)
                    for (let j = 0; j < N_GRID; j++)
                      for (let k = 0; k < N_SOLAR; k++) acc += T[p][g][s][i][j][k] * vSlice[i][j][k];
                  expFuture += prob * acc;
                }
                total[p][g][s] = cost + gamma * expFuture;
              }
            }
          }

          if (best === null) {
            best = total;
            for (let p = 0; p < N_PRICE; p++)
              for (let g = 0; g < N_GRID; g++)
                for (let s = 0; s < N_SOLAR; s++) bestAction[p][g][s] = aIdx;
          } else {
            for (let p = 0; p < N_PRICE; p++) {
              for (let g = 0; g < N_GRID; g++) {
                for (let s = 0; s < N_SOLAR; s++) {
                  if (total[p][g][s] < best[p][g][s]) {
                    best[p][g][s] = total[p][g][s];
                    bestAction[p][g][s] = aIdx;
                  }
                }
              }
            }
          }
        });

        V[t][socIdx] = best;
        policy[t][socIdx] = bestAction;
      }
    }

    return {
      V: V, policy: policy, actions: actions,
      actionKw: function (t, socPct, p, g, s) {
        t = Math.max(0, Math.min(policy.length - 1, t));
        const socIdx = nearestSocBucket(socPct);
        return actions[policy[t][socIdx][p][g][s]];
      },
    };
  }

  const _policyCache = new Map();
  function getOrSolvePolicy(config, weights, targetSocPct, minSafeSocPct) {
    const key = JSON.stringify([
      config.batteryCapacityKwh, config.maxChargeRateKw, config.slotMinutes,
      config.horizonSlots, weights, targetSocPct, minSafeSocPct,
    ]);
    if (_policyCache.has(key)) return _policyCache.get(key);
    const solved = solveValueIteration(config, weights, targetSocPct, minSafeSocPct);
    _policyCache.set(key, solved);
    return solved;
  }

  // ---- Charging Opportunity Score (mirrors optimization/station_optimizer.py) ----
  const COS_PROFILE_WEIGHTS = {
    save_money: { cost: 3.0, time: 0.5, queue: 0.5, distance: 0.5, battery: 0.5, grid: 0.5, renewable: 0.5, availability: 0.5 },
    fastest: { cost: 0.3, time: 3.0, queue: 2.0, distance: 2.0, battery: 0.2, grid: 0.2, renewable: 0.2, availability: 1.5 },
    battery_health: { cost: 0.5, time: 0.5, queue: 0.5, distance: 0.5, battery: 3.0, grid: 0.5, renewable: 0.5, availability: 0.5 },
    green: { cost: 0.5, time: 0.5, queue: 0.5, distance: 0.5, battery: 0.5, grid: 0.5, renewable: 3.0, availability: 0.5 },
    balanced: { cost: 1.0, time: 1.0, queue: 1.0, distance: 1.0, battery: 1.0, grid: 1.0, renewable: 1.0, availability: 1.0 },
    custom: { cost: 1.0, time: 1.0, queue: 1.0, distance: 1.0, battery: 1.0, grid: 1.0, renewable: 1.0, availability: 1.0 },
  };
  function minmaxGoodness(values, higherIsBetter) {
    const lo = Math.min.apply(null, values), hi = Math.max.apply(null, values);
    if (hi - lo < 1e-12) return values.map(() => 1.0);
    return values.map((v) => (higherIsBetter ? (v - lo) / (hi - lo) : (hi - v) / (hi - lo)));
  }
  function computeCosScores(candidates, weights) {
    if (!candidates.length) return {};
    const cost = minmaxGoodness(candidates.map((c) => c.chargingCost), false);
    const time = minmaxGoodness(candidates.map((c) => c.travelTimeMin + c.chargingDurationMin), false);
    const queue = minmaxGoodness(candidates.map((c) => c.predictedWaitMin), false);
    const distance = minmaxGoodness(candidates.map((c) => c.distanceKm), false);
    const battery = minmaxGoodness(candidates.map((c) => c.batteryImpact), false);
    const grid = minmaxGoodness(candidates.map((c) => c.gridLoadPct), false);
    const renewable = minmaxGoodness(candidates.map((c) => c.renewableAvailability), true);
    const availability = minmaxGoodness(candidates.map((c) => c.connectorAvailabilityFrac), true);
    let totalW = 0;
    for (const k in weights) totalW += weights[k];

    const scores = {};
    candidates.forEach((c, i) => {
      const sum =
        weights.cost * cost[i] + weights.time * time[i] + weights.queue * queue[i] +
        weights.distance * distance[i] + weights.battery * battery[i] + weights.grid * grid[i] +
        weights.renewable * renewable[i] + weights.availability * availability[i];
      scores[c.stationId] = Math.round(((100 * sum) / totalW) * 10) / 10;
    });
    return scores;
  }
  function rankStations(candidates, profile) {
    const weights = COS_PROFILE_WEIGHTS[profile] || COS_PROFILE_WEIGHTS.balanced;
    const scores = computeCosScores(candidates, weights);
    return candidates
      .map((c) => [c, scores[c.stationId]])
      .sort((a, b) => b[1] - a[1]);
  }

  // ---- Journey energy model (mirrors services/journey_service.py) ----
  const SAFETY_MARGIN_FRACTION = 0.15;
  function round1(x) { return Math.round(x * 10) / 10; }
  function round2(x) { return Math.round(x * 100) / 100; }
  function estimateJourneyEnergy(distanceKm, vehicle, trafficMultiplier, elevationGainM) {
    if (trafficMultiplier === undefined) trafficMultiplier = 1.0;
    if (elevationGainM === undefined) elevationGainM = 0.0;
    const baseEnergy = distanceKm * vehicle.efficiencyKwhPerKm * trafficMultiplier;
    const elevationEnergy = elevationGainM * 0.00025;
    const energyRequiredKwh = baseEnergy + elevationEnergy;
    const socConsumedPct = (energyRequiredKwh / vehicle.batteryCapacityKwh) * 100.0;
    const expectedArrivalSocPct = vehicle.currentSocPct - socConsumedPct;
    const minSafeSocPct = Math.max(0, ((SAFETY_MARGIN_FRACTION * energyRequiredKwh) / vehicle.batteryCapacityKwh) * 100.0);
    const isFeasible = expectedArrivalSocPct >= minSafeSocPct;
    const shortfall = Math.max(0, minSafeSocPct - expectedArrivalSocPct);
    return {
      energyRequiredKwh: round2(energyRequiredKwh),
      expectedArrivalSocPct: round1(expectedArrivalSocPct),
      minSafeSocPct: round1(minSafeSocPct),
      isFeasible: isFeasible,
      shortfallPct: round1(shortfall),
    };
  }

  // ---- Explainability (mirrors optimization/explainability.py) ----
  function buildExplanation(ctx) {
    const reasons = [];
    if (!ctx.isFeasible && ctx.maxAchievableSocPct != null) {
      reasons.push({
        code: "target_infeasible",
        text:
          ctx.targetSocPct.toFixed(0) +
          "% is not achievable before your deadline — the maximum achievable charge is " +
          ctx.maxAchievableSocPct.toFixed(0) + "%.",
      });
    }
    if (ctx.recommendedAction === "wait" && ctx.predictedBestPriceValue != null && ctx.currentPriceValue) {
      const pctLower = (1 - ctx.predictedBestPriceValue / ctx.currentPriceValue) * 100;
      if (pctLower > 1) {
        reasons.push({
          code: "electricity_price_advantage",
          text:
            "Waiting until " + (ctx.predictedBestTimeLabel || "later") +
            " is recommended because the predicted electricity price is " + pctLower.toFixed(0) + "% lower than right now.",
        });
      }
    }
    if (ctx.currentGridIdx >= 1 && ctx.recommendedAction === "wait") {
      reasons.push({
        code: "grid_load_advantage",
        text: "Grid demand is currently " + GRID_LEVELS[ctx.currentGridIdx] +
          " and is expected to ease, so charging later reduces strain on the shared grid.",
      });
    }
    if (ctx.renewableAvailabilityFrac != null && ctx.renewableAvailabilityFrac > 0.3) {
      reasons.push({
        code: "renewable_availability",
        text: "About " + (ctx.renewableAvailabilityFrac * 100).toFixed(0) +
          "% of this charging session could be sourced from solar generation.",
      });
    }
    if (ctx.isFeasible) {
      reasons.push({
        code: "deadline_feasibility",
        text: "Your " + ctx.targetSocPct.toFixed(0) + "% target remains achievable" +
          (ctx.finishTimeLabel ? " before " + ctx.finishTimeLabel + "." : "."),
      });
    }
    if (ctx.batteryDegradationEstimate != null && ["wait", "charge_partial"].indexOf(ctx.recommendedAction) !== -1) {
      reasons.push({
        code: "battery_health_advantage",
        text: "This charging pattern is gentler on your battery than charging at full power immediately.",
      });
    }
    if (ctx.estimatedCost != null && ctx.immediateCost != null && ctx.immediateCost > 0) {
      const savings = ctx.immediateCost - ctx.estimatedCost;
      if (savings > 0.5) {
        reasons.push({
          code: "cost_savings",
          text: "This plan costs an estimated ₹" + ctx.estimatedCost.toFixed(0) + ", ₹" + savings.toFixed(0) +
            " less than charging immediately (₹" + ctx.immediateCost.toFixed(0) + ").",
        });
      }
    }
    if (!reasons.length) {
      reasons.push({
        code: "default_price_context",
        text: "Current electricity price is " + PRICE_LEVELS[ctx.currentPriceIdx] +
          " and grid demand is " + GRID_LEVELS[ctx.currentGridIdx] + ".",
      });
    }
    return reasons;
  }

  // ---- Synthetic 24h curves (mirrors ml/data_synthesis.py, deterministic) ----
  function seededRandom(seed) {
    let s = seed % 2147483647;
    if (s <= 0) s += 2147483646;
    return function () {
      s = (s * 16807) % 2147483647;
      return s / 2147483647;
    };
  }
  function gaussianBump(hour, center, width) {
    return Math.exp(-Math.pow(hour - center, 2) / (2 * width * width));
  }
  function generateDayCurves(seed) {
    if (seed === undefined) seed = 7;
    const rand = seededRandom(seed);
    const hours = [];
    for (let h = 0; h < 24; h++) hours.push(h);
    const price = hours.map((h) => {
      const base = 8.0 + 3.0 * gaussianBump(h, 9, 2.0) + 4.5 * gaussianBump(h, 19, 2.5);
      return Math.max(2.5, Math.min(20, base + (rand() - 0.5) * 1.2));
    });
    const grid = hours.map((h) => {
      const base = 45.0 + 15.0 * gaussianBump(h, 9, 2.0) + 25.0 * gaussianBump(h, 19, 2.5);
      return Math.max(10, Math.min(98, base + (rand() - 0.5) * 8));
    });
    const solar = hours.map((h) => {
      const daylight = Math.max(0, Math.sin((Math.PI * (h - 6)) / 12));
      return Math.max(0, Math.min(8, daylight * 8 * 0.85 + (rand() - 0.5) * 0.3));
    });
    return { hours: hours, price: price, grid: grid, solar: solar };
  }

  return {
    SOC_STEP: SOC_STEP, N_SOC: N_SOC, PRICE_LEVELS: PRICE_LEVELS, GRID_LEVELS: GRID_LEVELS, SOLAR_LEVELS: SOLAR_LEVELS,
    DEFAULT_ACTIONS_KW: DEFAULT_ACTIONS_KW, DEFAULT_PRICE_VALUES: DEFAULT_PRICE_VALUES,
    DEFAULT_GRID_LOAD_VALUES: DEFAULT_GRID_LOAD_VALUES, DEFAULT_SOLAR_AVAIL_VALUES: DEFAULT_SOLAR_AVAIL_VALUES,
    MDPConfig: MDPConfig, TransitionModel: TransitionModel,
    socFromBucket: socFromBucket, nearestSocBucket: nearestSocBucket,
    bucketizePrice: bucketizePrice, bucketizeGrid: bucketizeGrid, bucketizeSolar: bucketizeSolar,
    resolveWeights: resolveWeights, realElectricityCost: realElectricityCost, PROFILE_WEIGHTS: PROFILE_WEIGHTS,
    computeDegradationCost: computeDegradationCost, batteryHealthIndicator: batteryHealthIndicator,
    solveValueIteration: solveValueIteration, getOrSolvePolicy: getOrSolvePolicy,
    computeCosScores: computeCosScores, rankStations: rankStations, COS_PROFILE_WEIGHTS: COS_PROFILE_WEIGHTS,
    estimateJourneyEnergy: estimateJourneyEnergy,
    buildExplanation: buildExplanation,
    generateDayCurves: generateDayCurves, seededRandom: seededRandom,
  };
})();

if (typeof module !== "undefined") module.exports = Engine;
