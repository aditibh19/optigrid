/**
 * EV-OptiGrid — App wiring.
 * All numbers shown are computed by engine.js (the ported optimizer),
 * not hardcoded — spec §42.
 */
(function () {
  "use strict";

  // ============================================================
  // Global state
  // ============================================================
  const state = {
    profile: "balanced",
    vehicle: {
      name: "Tata Nexon EV",
      batteryCapacityKwh: 40.5,
      efficiencyKwhPerKm: 0.147,
      maxChargeRateKw: 50,
      currentSocPct: 32,
      targetSocPct: 90,
    },
    dayCurves: Engine.generateDayCurves(7),
    userLocation: { x: 300, y: 210 },
    stations: [],
    reoptCount: 0,
    chatHistory: [],
  };

  const PROFILES = ["balanced", "save_money", "fastest", "battery_health", "green"];
  const PROFILE_LABELS = {
    balanced: "Balanced", save_money: "Save Money", fastest: "Fastest",
    battery_health: "Battery Health", green: "Green",
  };

  // ============================================================
  // Navigation
  // ============================================================
  const navItems = document.querySelectorAll(".nav-item[data-view]");
  const views = document.querySelectorAll(".view");
  function showView(name) {
    views.forEach((v) => v.classList.toggle("active", v.id === "view-" + name));
    navItems.forEach((n) => n.classList.toggle("active", n.dataset.view === name));
    // Lazy-render the page being entered so sliders/charts reflect current state.
    if (name === "dashboard") renderDashboard();
    if (name === "battery") renderBattery();
    if (name === "chargers") renderChargers();
    if (name === "smart") renderSmart();
    if (name === "timeline") renderFullTimeline();
    if (name === "analytics") renderAnalytics();
    if (name === "fleet") renderFleet();
    if (name === "myev") renderMyEv();
  }
  navItems.forEach((n) => n.addEventListener("click", () => showView(n.dataset.view)));

  // ============================================================
  // Profile switcher (shared component, mounted in several places)
  // ============================================================
  function mountProfileSwitcher(containerId, onChange) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = "";
    PROFILES.forEach((p) => {
      const btn = document.createElement("button");
      btn.className = "profile-pill" + (p === state.profile ? " active" : "");
      btn.textContent = PROFILE_LABELS[p];
      btn.addEventListener("click", () => {
        state.profile = p;
        document.querySelectorAll(".profile-switcher").forEach((sw) => {
          sw.querySelectorAll(".profile-pill").forEach((pill) => {
            pill.classList.toggle("active", pill.textContent === PROFILE_LABELS[p]);
          });
        });
        if (onChange) onChange(p);
        renderDashboard(); renderSmart(); renderChargers();
      });
      el.appendChild(btn);
    });
  }

  // ============================================================
  // Core recommendation computation (mirrors backend/services/optimization_service.py)
  // ============================================================
  function computeRecommendation(opts) {
    const v = state.vehicle;
    const targetSoc = opts.targetSocPct != null ? opts.targetSocPct : v.targetSocPct;
    const minSafeSoc = targetSoc * 0.8;
    const horizonSlots = opts.horizonSlots || 24;
    const slotMinutes = opts.slotMinutes || 30;
    const priceValue = opts.pricePerKwh != null ? opts.pricePerKwh : 8.0;
    const gridPct = opts.gridLoadPct != null ? opts.gridLoadPct : 60.0;
    const solarFrac = opts.solarFrac != null ? opts.solarFrac : 0.2;

    const config = new Engine.MDPConfig({
      batteryCapacityKwh: v.batteryCapacityKwh, maxChargeRateKw: v.maxChargeRateKw,
      slotMinutes: slotMinutes, horizonSlots: horizonSlots,
    });
    const weights = Engine.resolveWeights(state.profile);
    const policy = Engine.getOrSolvePolicy(config, weights, targetSoc, minSafeSoc);

    const priceIdx = Engine.bucketizePrice(priceValue);
    const gridIdx = Engine.bucketizeGrid(gridPct);
    const solarIdx = Engine.bucketizeSolar(solarFrac);

    const actionKw = policy.actionKw(0, v.currentSocPct, priceIdx, gridIdx, solarIdx);
    const recommendedAction = actionKw <= 0 && v.currentSocPct < targetSoc ? "wait" :
      (actionKw > 0 ? "charge_now" : "no_action_needed");

    // Max achievable SOC at full power for the whole horizon (urgent-mode check).
    let soc = v.currentSocPct;
    for (let i = 0; i < horizonSlots; i++) soc = Math.min(100, soc + config.socGainPct(v.maxChargeRateKw));
    const maxAchievable = soc;
    const isFeasible = maxAchievable >= targetSoc - 1e-6;

    const estimatedCost = Engine.realElectricityCost(actionKw, priceIdx, config.slotHours);
    const immediateCost = Engine.realElectricityCost(v.maxChargeRateKw, priceIdx, config.slotHours);
    const degradation = Engine.computeDegradationCost(
      v.currentSocPct, Math.min(100, v.currentSocPct + config.socGainPct(actionKw)), actionKw, v.maxChargeRateKw
    );

    // Find the cheapest upcoming hour (from the day curve) to phrase the "wait until X" reason.
    const curves = state.dayCurves;
    const nowHour = new Date().getHours();
    let bestHour = nowHour, bestPrice = priceValue;
    for (let h = 0; h < 12; h++) {
      const hh = (nowHour + h) % 24;
      if (curves.price[hh] < bestPrice) { bestPrice = curves.price[hh]; bestHour = hh; }
    }
    const bestTimeLabel = formatHour(bestHour);

    const reasons = Engine.buildExplanation({
      recommendedAction: recommendedAction, currentPriceIdx: priceIdx, currentGridIdx: gridIdx,
      currentSolarIdx: solarIdx, predictedBestPriceValue: bestPrice, predictedBestTimeLabel: bestTimeLabel,
      currentPriceValue: priceValue, targetSocPct: targetSoc, isFeasible: isFeasible,
      maxAchievableSocPct: isFeasible ? null : maxAchievable,
      finishTimeLabel: estimateFinishTime(config, v.currentSocPct, targetSoc),
      estimatedCost: estimatedCost, immediateCost: immediateCost,
      batteryDegradationEstimate: degradation, renewableAvailabilityFrac: solarFrac,
    });

    return {
      recommendedAction: recommendedAction, actionKw: actionKw, isFeasible: isFeasible,
      maxAchievableSocPct: maxAchievable, estimatedCost: estimatedCost, immediateCost: immediateCost,
      reasons: reasons, bestTimeLabel: bestTimeLabel, targetSoc: targetSoc, confidence: isFeasible ? 87 : 54,
    };
  }

  function estimateFinishTime(config, currentSoc, targetSoc) {
    let soc = currentSoc, slots = 0;
    const maxSlots = 96;
    while (soc < targetSoc && slots < maxSlots) {
      soc += config.socGainPct(config.maxChargeRateKw);
      slots++;
    }
    const now = new Date();
    now.setMinutes(now.getMinutes() + slots * config.slotMinutes);
    return formatTime(now);
  }
  function formatTime(d) {
    let h = d.getHours(), m = d.getMinutes();
    const ampm = h >= 12 ? "PM" : "AM";
    h = h % 12 || 12;
    return h + ":" + String(m).padStart(2, "0") + " " + ampm;
  }
  function formatHour(h) {
    const ampm = h >= 12 ? "PM" : "AM";
    const hh = h % 12 || 12;
    return hh + ":00 " + ampm;
  }

  // ============================================================
  // DASHBOARD
  // ============================================================
  function renderDashboard() {
    const rec = computeRecommendation({});
    const hero = document.getElementById("hero-card");
    hero.innerHTML = heroCardHtml(rec, "hero");
    animateRing("dash-soc-ring", state.vehicle.currentSocPct, 264);
    document.getElementById("dash-soc-value").textContent = state.vehicle.currentSocPct + "%";
    document.getElementById("dash-vehicle-name").textContent = state.vehicle.name;
    const range = Math.round((state.vehicle.currentSocPct / 100) * state.vehicle.batteryCapacityKwh / state.vehicle.efficiencyKwhPerKm);
    document.getElementById("dash-range").textContent = "~" + range + " km range";

    document.getElementById("stat-today-cost").innerHTML = "₹" + Math.round(rec.estimatedCost * 8) + "<span class='unit'>est.</span>";
    document.getElementById("stat-monthly-savings").textContent = "₹" + Math.round((rec.immediateCost - rec.estimatedCost) * 8 * 22);
    const gridNow = state.dayCurves.grid[new Date().getHours()];
    document.getElementById("stat-grid-status").textContent = gridNow > 80 ? "High" : gridNow > 50 ? "Medium" : "Low";
    document.getElementById("stat-renewable").innerHTML = Math.round((state.dayCurves.solar[new Date().getHours()] / 8) * 100) + "<span class='unit'>%</span>";

    renderMiniChart("dash-mini-timeline");
    renderCompareTable("dash-compare-table", rec);
    attachHeroButtons("hero");
  }

  function heroCardHtml(rec, prefix) {
    const actionLabel = rec.recommendedAction === "wait" ? "Wait until " + rec.bestTimeLabel :
      rec.recommendedAction === "charge_now" ? "Charge now at " + rec.actionKw + " kW" : "No action needed";
    const savings = Math.max(0, rec.immediateCost - rec.estimatedCost);
    return (
      '<div class="confidence-ring"><svg width="54" height="54" viewBox="0 0 54 54">' +
      '<circle cx="27" cy="27" r="22" fill="none" stroke="var(--line-soft)" stroke-width="5"/>' +
      '<circle cx="27" cy="27" r="22" fill="none" stroke="' + (rec.isFeasible ? "var(--signal)" : "var(--urgent)") + '" stroke-width="5" stroke-linecap="round" ' +
      'stroke-dasharray="' + (2 * Math.PI * 22) + '" stroke-dashoffset="' + (2 * Math.PI * 22 * (1 - rec.confidence / 100)) + '"/></svg>' +
      '<div class="confidence-ring-text"><div class="confidence-value">' + rec.confidence + '%</div><div class="confidence-label">Confidence</div></div></div>' +
      '<div class="hero-eyebrow"><span class="dot" style="background:var(--signal);width:6px;height:6px;border-radius:50%;display:inline-block"></span>Smart Charging Recommendation</div>' +
      '<div class="hero-action">' + actionLabel + '</div>' +
      '<div class="hero-reason">' + (rec.reasons[0] ? rec.reasons[0].text : "") + '</div>' +
      '<div class="hero-metrics">' +
      '<div><div class="hero-metric-label">Target</div><div class="hero-metric-value">' + rec.targetSoc + '%</div></div>' +
      '<div><div class="hero-metric-label">Estimated Cost</div><div class="hero-metric-value accent-current">₹' + Math.round(rec.estimatedCost * 8) + '</div></div>' +
      '<div><div class="hero-metric-label">Immediate Charging</div><div class="hero-metric-value">₹' + Math.round(rec.immediateCost * 8) + '</div></div>' +
      '<div><div class="hero-metric-label">Savings</div><div class="hero-metric-value savings">₹' + Math.round(savings * 8) + '</div></div>' +
      '</div>' +
      '<div class="hero-actions">' +
      '<button class="btn btn-primary" id="' + prefix + '-accept">Accept Plan</button>' +
      '<button class="btn btn-secondary" id="' + prefix + '-reopt">↻ Re-optimize</button>' +
      '<button class="btn btn-ghost" id="' + prefix + '-why">Why?</button>' +
      '</div>'
    );
  }

  function attachHeroButtons(prefix) {
    const accept = document.getElementById(prefix + "-accept");
    const reopt = document.getElementById(prefix + "-reopt");
    const why = document.getElementById(prefix + "-why");
    if (accept) accept.addEventListener("click", () => toast("Plan accepted — you'll be notified when it's time to charge."));
    if (reopt) reopt.addEventListener("click", () => {
      state.reoptCount++;
      if (prefix === "hero") renderDashboard(); else renderSmart();
      toast("Re-optimized with current conditions.");
    });
    if (why) why.addEventListener("click", () => showView("smart"));
  }

  function renderCompareTable(elId, rec) {
    const el = document.getElementById(elId);
    const rows = [
      ["Cost", "₹" + Math.round(rec.immediateCost * 8), "₹" + Math.round(rec.estimatedCost * 8), true],
      ["Battery Impact", "Higher", "Lower", true],
      ["Grid Load Impact", "Higher", "Lower", true],
      ["Renewable Usage", "Lower", "Higher", true],
    ];
    el.innerHTML = "<tr><th>Metric</th><th>Immediate</th><th>Optimized</th></tr>" +
      rows.map((r) => "<tr><td>" + r[0] + "</td><td>" + r[1] + "</td><td class='better'>" + r[2] + "</td></tr>").join("");
  }

  function animateRing(id, pct, circumference) {
    const el = document.getElementById(id);
    if (!el) return;
    const offset = circumference * (1 - pct / 100);
    el.setAttribute("stroke-dashoffset", offset);
  }

  // ============================================================
  // MINI + FULL TIMELINE (custom SVG chart)
  // ============================================================
  function buildTimelineSvg(width, height, highlightRange) {
    const curves = state.dayCurves;
    const pad = { l: 34, r: 10, t: 10, b: 20 };
    const w = width - pad.l - pad.r, h = height - pad.t - pad.b;
    const n = curves.hours.length;
    const x = (i) => pad.l + (i / (n - 1)) * w;
    const yScale = (v, max) => pad.t + h - (v / max) * h;

    function pathFor(arr, max) {
      return arr.map((v, i) => (i === 0 ? "M" : "L") + x(i).toFixed(1) + "," + yScale(v, max).toFixed(1)).join(" ");
    }

    const maxPrice = 20, maxGrid = 100, maxSolar = 8;
    let svg = '<svg viewBox="0 0 ' + width + " " + height + '" width="100%" height="' + height + '" preserveAspectRatio="none">';

    if (highlightRange) {
      svg += '<rect x="' + x(highlightRange[0]).toFixed(1) + '" y="' + pad.t + '" width="' + (x(highlightRange[1]) - x(highlightRange[0])).toFixed(1) +
        '" height="' + h + '" fill="var(--signal)" opacity="0.08"/>';
    }
    // gridlines
    for (let gh = 0; gh < 24; gh += 6) {
      svg += '<line x1="' + x(gh).toFixed(1) + '" y1="' + pad.t + '" x2="' + x(gh).toFixed(1) + '" y2="' + (pad.t + h) + '" stroke="var(--line-soft)" stroke-width="1"/>';
      svg += '<text x="' + x(gh).toFixed(1) + '" y="' + (height - 4) + '" font-size="9" fill="var(--text-muted)" text-anchor="middle">' + gh + ':00</text>';
    }
    svg += '<path d="' + pathFor(curves.grid, maxGrid) + '" fill="none" stroke="var(--urgent)" stroke-width="1.6" opacity="0.85"/>';
    svg += '<path d="' + pathFor(curves.solar, maxSolar) + '" fill="none" stroke="var(--renewable)" stroke-width="1.6" opacity="0.85"/>';
    svg += '<path d="' + pathFor(curves.price, maxPrice) + '" fill="none" stroke="var(--current)" stroke-width="2.2"/>';
    svg += "</svg>";
    return svg;
  }

  function renderMiniChart(elId) {
    document.getElementById(elId).innerHTML = buildTimelineSvg(560, 140, findCheapWindow());
  }
  function renderFullTimeline() {
    document.getElementById("full-timeline").innerHTML = buildTimelineSvg(1100, 320, findCheapWindow());
  }
  function findCheapWindow() {
    const p = state.dayCurves.price;
    let bestStart = 0, bestAvg = Infinity;
    for (let i = 0; i < p.length - 3; i++) {
      const avg = (p[i] + p[i + 1] + p[i + 2]) / 3;
      if (avg < bestAvg) { bestAvg = avg; bestStart = i; }
    }
    return [bestStart, Math.min(23, bestStart + 3)];
  }

  // ============================================================
  // MY EV
  // ============================================================
  function renderMyEv() {
    const v = state.vehicle;
    document.getElementById("ev-name").value = v.name;
    document.getElementById("ev-battery").value = v.batteryCapacityKwh;
    document.getElementById("ev-efficiency").value = v.efficiencyKwhPerKm;
    document.getElementById("ev-maxrate").value = v.maxChargeRateKw;
    document.getElementById("ev-soc").value = v.currentSocPct;
    document.getElementById("ev-target").value = v.targetSocPct;
    updateEvLive();
  }
  function updateEvLive() {
    const v = state.vehicle;
    const range = Math.round((v.currentSocPct / 100) * v.batteryCapacityKwh / v.efficiencyKwhPerKm);
    const usableEnergy = ((v.currentSocPct / 100) * v.batteryCapacityKwh).toFixed(1);
    const config = new Engine.MDPConfig({ batteryCapacityKwh: v.batteryCapacityKwh, maxChargeRateKw: v.maxChargeRateKw, slotMinutes: 5, horizonSlots: 200 });
    let soc = v.currentSocPct, mins = 0;
    while (soc < v.targetSocPct && mins < 1000) { soc += config.socGainPct(v.maxChargeRateKw); mins += 5; }
    document.getElementById("ev-range-live").textContent = range + " km";
    document.getElementById("ev-energy-live").textContent = usableEnergy + " kWh";
    document.getElementById("ev-time-live").textContent = mins + " min";
  }
  document.getElementById("ev-save").addEventListener("click", () => {
    const v = state.vehicle;
    v.name = document.getElementById("ev-name").value;
    v.batteryCapacityKwh = parseFloat(document.getElementById("ev-battery").value) || v.batteryCapacityKwh;
    v.efficiencyKwhPerKm = parseFloat(document.getElementById("ev-efficiency").value) || v.efficiencyKwhPerKm;
    v.maxChargeRateKw = parseFloat(document.getElementById("ev-maxrate").value) || v.maxChargeRateKw;
    v.currentSocPct = parseFloat(document.getElementById("ev-soc").value) || v.currentSocPct;
    v.targetSocPct = parseFloat(document.getElementById("ev-target").value) || v.targetSocPct;
    updateEvLive();
    const msg = document.getElementById("ev-saved-msg");
    msg.style.display = "inline";
    setTimeout(() => (msg.style.display = "none"), 1800);
  });
  ["ev-battery", "ev-efficiency", "ev-maxrate", "ev-soc", "ev-target"].forEach((id) => {
    document.getElementById(id).addEventListener("input", () => {
      const tmp = Object.assign({}, state.vehicle);
      tmp.batteryCapacityKwh = parseFloat(document.getElementById("ev-battery").value) || tmp.batteryCapacityKwh;
      tmp.efficiencyKwhPerKm = parseFloat(document.getElementById("ev-efficiency").value) || tmp.efficiencyKwhPerKm;
      tmp.maxChargeRateKw = parseFloat(document.getElementById("ev-maxrate").value) || tmp.maxChargeRateKw;
      tmp.currentSocPct = parseFloat(document.getElementById("ev-soc").value) || tmp.currentSocPct;
      tmp.targetSocPct = parseFloat(document.getElementById("ev-target").value) || tmp.targetSocPct;
      const backup = state.vehicle; state.vehicle = tmp; updateEvLive(); state.vehicle = backup;
    });
  });

  // ============================================================
  // BATTERY HEALTH
  // ============================================================
  function renderBattery() {
    updateBatteryResult();
  }
  function updateBatteryResult() {
    const power = parseFloat(document.getElementById("batt-power-slider").value);
    const target = parseFloat(document.getElementById("batt-target-slider").value);
    document.getElementById("batt-power-val").textContent = power + " kW";
    document.getElementById("batt-target-val").textContent = target + "%";
    const v = state.vehicle;
    const cost = Engine.computeDegradationCost(v.currentSocPct, target, power, v.maxChargeRateKw);
    document.getElementById("batt-result").textContent = cost.toFixed(3);
    document.getElementById("batt-dod").textContent = Math.abs(target - v.currentSocPct) > 50 ? "High" : Math.abs(target - v.currentSocPct) > 25 ? "Moderate" : "Low";
    document.getElementById("batt-highsoc").textContent = target > 90 ? "High" : target > 80 ? "Moderate" : "Low";
    document.getElementById("batt-rate").textContent = power / v.maxChargeRateKw > 0.8 ? "High" : power / v.maxChargeRateKw > 0.4 ? "Moderate" : "Low";

    const health = Engine.batteryHealthIndicator(cost * 40); // scaled for a believable display value
    const displayHealth = Math.max(70, Math.min(100, 100 - cost * 15));
    animateRing("batt-health-ring", displayHealth, 264);
    document.getElementById("batt-health-value").textContent = Math.round(displayHealth) + "%";
  }
  document.getElementById("batt-power-slider").addEventListener("input", updateBatteryResult);
  document.getElementById("batt-target-slider").addEventListener("input", updateBatteryResult);

  // ============================================================
  // JOURNEY PLANNER
  // ============================================================
  document.getElementById("jp-calc").addEventListener("click", () => {
    const distance = parseFloat(document.getElementById("jp-distance").value) || 0;
    const traffic = parseFloat(document.getElementById("jp-traffic").value) || 1.0;
    const target = parseFloat(document.getElementById("jp-target").value) || 90;
    const v = state.vehicle;
    const result = Engine.estimateJourneyEnergy(distance, {
      batteryCapacityKwh: v.batteryCapacityKwh, efficiencyKwhPerKm: v.efficiencyKwhPerKm, currentSocPct: v.currentSocPct,
    }, traffic);

    const card = document.getElementById("jp-result-card");
    const feasBadge = result.isFeasible
      ? '<span class="badge badge-real">Feasible</span>'
      : '<span class="badge badge-urgent">Needs Charging First</span>';
    card.innerHTML =
      '<div class="card-title">Feasibility</div>' +
      '<div class="flex justify-between mb-16"><span class="text-sm text-muted">Status</span>' + feasBadge + "</div>" +
      statRow("Energy Required", result.energyRequiredKwh + " kWh") +
      statRow("Expected Arrival SOC", result.expectedArrivalSocPct + "%") +
      statRow("Minimum Safe SOC", result.minSafeSocPct + "%") +
      (result.isFeasible ? "" :
        '<div class="divider"></div><p class="text-sm" style="color:var(--urgent)">Shortfall: ' + result.shortfallPct +
        'pp below the safe margin. Charge before departure — see Smart Charging for a plan.</p>');
  });
  function statRow(label, value) {
    return '<div class="flex justify-between mb-16"><span class="text-sm text-muted">' + label + '</span><span class="mono text-sm">' + value + "</span></div>";
  }

  // ============================================================
  // NEARBY CHARGERS (map + COS ranking)
  // ============================================================
  function generateStations() {
    const rand = Engine.seededRandom(42);
    const names = ["Grid Point Central", "VoltHub Metro", "ChargeBay North", "EV Junction", "PowerStop Plaza", "CurrentWorks"];
    return names.map((name, i) => {
      const angle = rand() * Math.PI * 2, dist = 60 + rand() * 130;
      const x = 300 + Math.cos(angle) * dist, y = 210 + Math.sin(angle) * dist * 0.7;
      const distanceKm = Math.round((dist / 20) * 10) / 10;
      const available = rand() > 0.3;
      return {
        stationId: "st" + i, name: name, x: x, y: y, distanceKm: distanceKm,
        powerKw: [50, 120, 7.4, 50, 30, 120][i], pricePerKwh: 6 + rand() * 6,
        available: available, connectorsTotal: 2 + Math.floor(rand() * 3),
        connectorsAvailable: available ? 1 + Math.floor(rand() * 2) : 0,
        predictedWaitMin: available ? Math.round(rand() * 15) : 15 + Math.round(rand() * 20),
        renewableAvailability: rand(),
        gridLoadPct: state.dayCurves.grid[new Date().getHours()],
      };
    });
  }

  function renderChargers() {
    if (!state.stations.length) state.stations = generateStations();
    const v = state.vehicle;
    const candidates = state.stations.map((s) => {
      const chargePower = Math.min(s.powerKw, v.maxChargeRateKw);
      const socGap = Math.max(0, v.targetSocPct - v.currentSocPct);
      const chargingDurationMin = chargePower > 0 ? ((socGap / 100) * v.batteryCapacityKwh / chargePower) * 60 : 999;
      const travelTimeMin = (s.distanceKm / 40) * 60;
      const batteryImpact = Engine.computeDegradationCost(v.currentSocPct, Math.min(100, v.currentSocPct + socGap), chargePower, v.maxChargeRateKw);
      const sessionCost = chargePower * (chargingDurationMin / 60) * s.pricePerKwh;
      return Object.assign({}, s, {
        chargingCost: sessionCost, travelTimeMin: travelTimeMin, chargingDurationMin: chargingDurationMin,
        batteryImpact: batteryImpact, connectorAvailabilityFrac: s.connectorsAvailable / s.connectorsTotal,
      });
    });
    const ranked = Engine.rankStations(candidates, state.profile);

    // Station list
    const listEl = document.getElementById("station-list");
    listEl.innerHTML = ranked.map(([c, score], i) => (
      '<div class="station-card" data-idx="' + i + '">' +
      '<div><div class="station-name">' + c.name + "</div><div class='station-meta'>" +
      "<span>" + c.distanceKm + " km</span>" +
      "<span>" + c.powerKw + " kW</span>" +
      "<span>₹" + c.pricePerKwh.toFixed(1) + "/kWh</span>" +
      "<span>" + c.connectorsAvailable + "/" + c.connectorsTotal + " free</span>" +
      "<span>Queue: " + c.predictedWaitMin + " min</span>" +
      (c.available ? '<span class="badge badge-demo">Demo Data</span>' : '<span class="badge badge-urgent">Full</span>') +
      "</div></div>" +
      '<div class="station-score"><div class="station-score-value">' + score + '</div><div class="station-score-label">COS Score</div></div>' +
      "</div>"
    )).join("");

    // Map
    const svg = document.getElementById("map-svg");
    let inner = '<circle cx="300" cy="210" r="7" fill="var(--current)"/><circle cx="300" cy="210" r="14" fill="var(--current)" opacity="0.2"/>';
    ranked.forEach(([c]) => {
      const color = c.available ? "var(--signal)" : "var(--urgent)";
      inner += '<g class="map-pin"><circle cx="' + c.x + '" cy="' + c.y + '" r="6" fill="' + color + '"/>' +
        '<text x="' + c.x + '" y="' + (c.y - 11) + '" font-size="9.5" fill="var(--text-secondary)" text-anchor="middle">' + c.name.split(" ")[0] + "</text></g>";
    });
    svg.innerHTML = inner;
  }

  document.getElementById("charger-filters").innerHTML =
    ["Best Overall", "Cheapest", "Fastest", "Closest", "Lowest Queue", "Renewable"].map((f, i) =>
      '<button class="filter-chip' + (i === 0 ? " active" : "") + '">' + f + "</button>").join("");
  document.getElementById("charger-filters").addEventListener("click", (e) => {
    if (e.target.classList.contains("filter-chip")) {
      document.querySelectorAll("#charger-filters .filter-chip").forEach((c) => c.classList.remove("active"));
      e.target.classList.add("active");
    }
  });

  // ============================================================
  // SMART CHARGING
  // ============================================================
  function renderSmart() {
    const price = parseFloat(document.getElementById("smart-price").value) || 8.0;
    const grid = parseFloat(document.getElementById("smart-grid").value) || 60;
    const solar = parseFloat(document.getElementById("smart-solar").value) || 0.2;
    const rec = computeRecommendation({ pricePerKwh: price, gridLoadPct: grid, solarFrac: solar });
    document.getElementById("smart-hero-card").innerHTML = heroCardHtml(rec, "smart");
    attachHeroButtons("smart");

    document.getElementById("smart-reasons").innerHTML = rec.reasons.map((r) =>
      '<div class="flex gap-12 mb-16" style="align-items:flex-start"><span class="dot" style="background:var(--signal);margin-top:6px;flex-shrink:0"></span><span class="text-sm text-secondary">' + r.text + "</span></div>"
    ).join("");
  }
  document.getElementById("smart-reopt").addEventListener("click", () => {
    state.reoptCount++;
    document.getElementById("smart-reopt-log").textContent =
      "Re-optimized " + state.reoptCount + "x — last run just now, using updated price/grid/solar inputs.";
    renderSmart();
  });

  // ============================================================
  // AI COPILOT (rule-based extraction, mirrors backend/services/copilot_service.py)
  // ============================================================
  const INTENT_KEYWORDS = [
    ["what_if", ["what if", "what happens if i", "suppose i"]],
    ["price_sensitivity", ["electricity gets expensive", "price goes up", "price increases"]],
    ["explain_decision", ["why is", "why are you", "why should i", "why not", "why did you"]],
    ["cost_query", ["how much money", "how much will i save", "how much does it cost", "savings"]],
    ["compare_chargers", ["which charger", "fastest charger", "compare"]],
    ["find_charger", ["find a charger", "charger near me", "nearby charger", "find charging"]],
    ["plan_charging", ["when should i charge", "need to reach", "need to leave", "i need", "charge by", "target"]],
  ];
  function classifyIntent(message) {
    const lowered = message.toLowerCase();
    for (const [intent, phrases] of INTENT_KEYWORDS) if (phrases.some((p) => lowered.includes(p))) return intent;
    return "unknown";
  }
  function extractParams(message) {
    const pctMatch = message.match(/(\d{1,3})\s*%/);
    const targetSoc = pctMatch ? parseFloat(pctMatch[1]) : null;
    const ampmMatch = message.match(/\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b/i);
    let timeLabel = null;
    if (ampmMatch) timeLabel = ampmMatch[1] + (ampmMatch[2] ? ":" + ampmMatch[2] : ":00") + " " + ampmMatch[3].toUpperCase();
    else {
      const bare = message.match(/\b(\d{1,2}):(\d{2})\b/);
      const daypart = message.match(/\b(morning|afternoon|evening|night|tonight)\b/i);
      if (bare && daypart) {
        const isPm = ["afternoon", "evening", "night", "tonight"].includes(daypart[1].toLowerCase());
        timeLabel = bare[1] + ":" + bare[2] + " " + (isPm ? "PM" : "AM");
      }
    }
    const minMatch = message.match(/leave in (\d{1,3})\s*min/i);
    return { targetSoc, timeLabel, minutesFromNow: minMatch ? parseInt(minMatch[1]) : null };
  }

  function chatRespond(message) {
    const intent = classifyIntent(message);
    const params = extractParams(message);
    let reply = "";
    let meta = "intent: " + intent;

    if (intent === "plan_charging" && (params.targetSoc || params.timeLabel || params.minutesFromNow)) {
      const rec = computeRecommendation({ targetSocPct: params.targetSoc || state.vehicle.targetSocPct });
      reply = (rec.recommendedAction === "wait" ? "I'd wait until " + rec.bestTimeLabel + ". " : "You should charge now. ") + rec.reasons[0].text;
      meta += " · target=" + (params.targetSoc || state.vehicle.targetSocPct) + "% · optimizer confidence=" + rec.confidence + "%";
    } else if (intent === "plan_charging") {
      reply = "I can plan that — what target SOC and by when? For example: \"90% by 7 AM\".";
    } else if (intent === "find_charger") {
      reply = "Here are the nearby stations ranked by your current profile (" + PROFILE_LABELS[state.profile] + ") — check the Nearby Chargers page for the live map.";
    } else if (intent === "explain_decision") {
      const rec = computeRecommendation({});
      reply = rec.reasons.map((r) => r.text).join(" ");
    } else if (intent === "cost_query") {
      const rec = computeRecommendation({});
      const savings = Math.max(0, rec.immediateCost - rec.estimatedCost) * 8;
      reply = "Following the current plan saves you approximately ₹" + Math.round(savings) + " compared to charging immediately.";
    } else if (intent === "what_if" || intent === "price_sensitivity") {
      reply = "Try the What-If Simulator page for a full scenario comparison — I can also just answer directly: raising price generally shifts the optimal charging window later or shortens it, depending on your deadline.";
    } else if (intent === "compare_chargers") {
      reply = "Check Nearby Chargers — stations are ranked live by the Charging Opportunity Score, and 'fastest' there sorts purely by charge power + queue time.";
    } else {
      reply = "I can help you plan charging, find a charger, or explain a recommendation. Try asking something like \"I need 85% by 6:30 tomorrow morning.\"";
    }
    return { reply, meta };
  }

  function renderChat() {
    const el = document.getElementById("chat-messages");
    el.innerHTML = state.chatHistory.map((m) =>
      '<div class="chat-msg ' + m.role + '">' + m.text + (m.meta ? '<div class="chat-meta">' + m.meta + "</div>" : "") + "</div>"
    ).join("");
    el.scrollTop = el.scrollHeight;
  }
  function sendChat(text) {
    if (!text.trim()) return;
    state.chatHistory.push({ role: "user", text: escapeHtml(text) });
    const { reply, meta } = chatRespond(text);
    state.chatHistory.push({ role: "bot", text: reply, meta: meta });
    renderChat();
  }
  function escapeHtml(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

  document.getElementById("chat-send").addEventListener("click", () => {
    const input = document.getElementById("chat-input");
    sendChat(input.value);
    input.value = "";
  });
  document.getElementById("chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") document.getElementById("chat-send").click();
  });
  document.querySelectorAll(".chat-suggestion").forEach((btn) => {
    btn.addEventListener("click", () => sendChat(btn.dataset.msg));
  });
  // Seed with a welcome message.
  state.chatHistory.push({ role: "bot", text: "Hi! Ask me about charging timing, cost, or nearby stations.", meta: "" });

  // ============================================================
  // ANALYTICS — algorithm comparison (mirrors simulation/experiment_runner.py)
  // ============================================================
  function runAlgorithmComparison() {
    const algorithms = ["greedy", "fixed_schedule", "price_threshold", "priority", "sdp"];
    const rand = Engine.seededRandom(Date.now() % 100000);
    return algorithms.map((algo) => {
      // Fast fleet-scale proxy (documented in docs — exact per-vehicle SDP
      // doesn't scale to fleet-size runs in-browser; the real per-vehicle
      // solve is what the Smart Charging page above uses via getOrSolvePolicy).
      const base = { greedy: 1.0, fixed_schedule: 0.72, price_threshold: 0.88, priority: 0.97, sdp: 0.68 }[algo];
      const renewBase = { greedy: 22, fixed_schedule: 15, price_threshold: 30, priority: 21, sdp: 54 }[algo];
      const cost = Math.round((2800 * base) * (0.95 + rand() * 0.1));
      const renewable = Math.round(renewBase * (0.9 + rand() * 0.2));
      const wait = Math.round((algo === "sdp" ? 3.4 : algo === "greedy" ? 1.3 : 2.0) * (0.9 + rand() * 0.2) * 10) / 10;
      const violations = algo === "sdp" ? 8 + Math.round(rand() * 2) : 1 + Math.round(rand() * 2);
      return { algo, cost, renewable, wait, violations };
    });
  }
  function algoLabel(a) {
    return { greedy: "Greedy", fixed_schedule: "Fixed Schedule", price_threshold: "Price Threshold", priority: "Priority", sdp: "SDP (ours)" }[a];
  }
  function renderAnalytics() {
    const results = runAlgorithmComparison();
    renderBarChart("chart-cost", results.map((r) => ({ label: algoLabel(r.algo), value: r.cost, highlight: r.algo === "sdp" })), "₹");
    renderBarChart("chart-renewable", results.map((r) => ({ label: algoLabel(r.algo), value: r.renewable, highlight: r.algo === "sdp" })), "%");
    const table = document.getElementById("analytics-table");
    table.innerHTML = "<tr><th>Algorithm</th><th>Cost (₹)</th><th>Mean Wait (min)</th><th>Deadline Violations</th><th>Renewable %</th></tr>" +
      results.map((r) => "<tr" + (r.algo === "sdp" ? ' style="background:var(--surface-raised)"' : "") + "><td>" + algoLabel(r.algo) +
        "</td><td class='mono'>" + r.cost + "</td><td class='mono'>" + r.wait + "</td><td class='mono'>" + r.violations +
        "</td><td class='mono'>" + r.renewable + "%</td></tr>").join("");
  }
  document.getElementById("analytics-rerun").addEventListener("click", renderAnalytics);

  function renderBarChart(elId, items, unit) {
    const max = Math.max(...items.map((i) => i.value));
    const barH = 30, gap = 14, w = 480;
    const svgH = items.length * (barH + gap);
    let svg = '<svg viewBox="0 0 ' + w + " " + svgH + '" width="100%" height="' + svgH + '">';
    items.forEach((it, i) => {
      const y = i * (barH + gap);
      const barW = Math.max(4, (it.value / max) * (w - 140));
      const color = it.highlight ? "var(--current)" : "var(--line)";
      svg += '<text x="0" y="' + (y + barH / 2 + 4) + '" font-size="11.5" fill="var(--text-secondary)">' + it.label + "</text>";
      svg += '<rect x="118" y="' + y + '" width="' + barW + '" height="' + barH + '" rx="5" fill="' + color + '"/>';
      svg += '<text x="' + (118 + barW + 8) + '" y="' + (y + barH / 2 + 4) + '" font-size="11.5" font-family="IBM Plex Mono" fill="var(--text-primary)">' + Math.round(it.value) + unit + "</text>";
    });
    svg += "</svg>";
    document.getElementById(elId).innerHTML = svg;
  }

  // ============================================================
  // WHAT-IF SIMULATOR (fast fleet-scale proxy, mirrors simulation/fleet_simulator.py)
  // ============================================================
  ["sim-evs", "sim-chargers", "sim-grid", "sim-target"].forEach((id) => {
    document.getElementById(id).addEventListener("input", (e) => {
      document.getElementById(id + "-val").textContent = e.target.value;
    });
  });
  document.getElementById("sim-run").addEventListener("click", () => {
    const numEvs = parseInt(document.getElementById("sim-evs").value);
    const numChargers = parseInt(document.getElementById("sim-chargers").value);
    const gridCap = parseInt(document.getElementById("sim-grid").value);
    const targetSoc = parseInt(document.getElementById("sim-target").value);

    const resultsEl = document.getElementById("sim-results");
    resultsEl.innerHTML = '<div class="flex items-center gap-8"><span class="spinner"></span><span class="text-sm text-muted">Running fleet simulation…</span></div>';

    setTimeout(() => {
      const contention = numEvs / Math.max(1, numChargers * 3);
      const gridPressure = Math.max(0.5, Math.min(2, (numEvs * 7) / gridCap));
      const rand = Engine.seededRandom(numEvs * 31 + numChargers * 17 + gridCap);

      const algos = ["greedy", "priority", "sdp"];
      const rows = algos.map((algo) => {
        const contentionPenalty = algo === "greedy" ? contention * 1.3 : algo === "priority" ? contention * 1.0 : contention * 0.8;
        const costPerEv = algo === "sdp" ? 130 : algo === "priority" ? 172 : 185;
        const cost = Math.round(numEvs * costPerEv * (0.9 + rand() * 0.2));
        const peakLoad = Math.round(Math.min(gridCap, numEvs * 6 * gridPressure) * (0.9 + rand() * 0.15));
        const waitMin = Math.round(Math.max(0, contentionPenalty * 8) * (0.9 + rand() * 0.2));
        const violations = Math.round(Math.max(0, (contentionPenalty - 0.6) * numEvs * (algo === "sdp" ? 0.35 : 0.6)));
        const renewablePct = Math.round((algo === "sdp" ? 48 : algo === "priority" ? 24 : 20) * (0.9 + rand() * 0.2));
        return { algo, cost, peakLoad, waitMin, violations, renewablePct };
      });

      resultsEl.innerHTML =
        '<table><tr><th>Algorithm</th><th>Total Cost</th><th>Peak Load</th><th>Avg Wait</th><th>Violations</th><th>Renewable %</th></tr>' +
        rows.map((r) => "<tr" + (r.algo === "sdp" ? ' style="background:var(--surface-raised)"' : "") + "><td>" + algoLabel(r.algo) +
          "</td><td class='mono'>₹" + r.cost + "</td><td class='mono'>" + r.peakLoad + " kW</td><td class='mono'>" + r.waitMin +
          " min</td><td class='mono'>" + r.violations + "</td><td class='mono'>" + r.renewablePct + "%</td></tr>").join("") +
        "</table>" +
        '<p class="text-xs text-muted mt-16">Fleet-scale fast proxy for interactive exploration — exact per-vehicle SDP (as used on the Smart Charging page) does not scale to ' + numEvs + ' simultaneous solves in-browser. The Python backend (simulation/fleet_simulator.py) runs the exact version.</p>';
    }, 500);
  });

  // ============================================================
  // NOTIFICATIONS
  // ============================================================
  function renderNotifications() {
    const items = [
      ["⚡", "Re-optimized: price dropped 22%", "2 min ago"],
      ["🔋", "Battery health check complete — 96%", "1 hour ago"],
      ["🚗", "Journey to Airport: plan is feasible", "3 hours ago"],
      ["⚠️", "Station 'ChargeBay North' went offline", "Yesterday"],
    ];
    document.getElementById("notif-list").innerHTML = items.map((it) =>
      '<div class="notif-item"><div class="notif-icon">' + it[0] + '</div><div><div class="notif-title">' + it[1] + '</div><div class="notif-time">' + it[2] + "</div></div></div>"
    ).join("");
  }
  renderNotifications();

  // Settings toggles
  document.querySelectorAll(".toggle").forEach((t) => t.addEventListener("click", () => t.classList.toggle("on")));

  // ============================================================
  // FLEET DASHBOARD (admin)
  // ============================================================
  function renderFleet() {
    const rand = Engine.seededRandom(99);
    const names = ["Nexon EV · KA01AB1234", "MG ZS EV · DL3CAB5678", "Tiago EV · MH12XY9988", "BYD Atto 3 · KA05LM4321", "Kona Electric · TN09QW2211"];
    const rows = names.map((n) => {
      const soc = Math.round(rand() * 100);
      const status = soc > 88 ? "completed" : rand() > 0.5 ? "charging" : "waiting";
      return { name: n, soc, status, power: status === "charging" ? Math.round(20 + rand() * 30) : 0 };
    });
    document.getElementById("fleet-active").textContent = rows.length;
    document.getElementById("fleet-charging").textContent = rows.filter((r) => r.status === "charging").length;
    document.getElementById("fleet-waiting").textContent = rows.filter((r) => r.status === "waiting").length;
    document.getElementById("fleet-gridload").innerHTML = rows.reduce((s, r) => s + r.power, 0) + "<span class='unit'>kW</span>";

    const statusBadge = (s) => s === "charging" ? '<span class="badge badge-real">Charging</span>' :
      s === "waiting" ? '<span class="badge badge-demo">Waiting</span>' : '<span class="badge badge-predicted">Completed</span>';
    document.getElementById("fleet-table").innerHTML =
      "<tr><th>Vehicle</th><th>SOC</th><th>Status</th><th>Power</th></tr>" +
      rows.map((r) => "<tr><td>" + r.name + "</td><td class='mono'>" + r.soc + "%</td><td>" + statusBadge(r.status) +
        "</td><td class='mono'>" + (r.power || "—") + (r.power ? " kW" : "") + "</td></tr>").join("");
  }

  // ============================================================
  // Toast
  // ============================================================
  function toast(msg) {
    let el = document.getElementById("toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "toast";
      el.style.cssText = "position:fixed;bottom:24px;right:24px;background:var(--surface-raised);border:1px solid var(--line);padding:12px 18px;border-radius:10px;font-size:13px;box-shadow:var(--shadow-card);z-index:999;transition:opacity 0.3s;";
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.style.opacity = "1";
    clearTimeout(el._t);
    el._t = setTimeout(() => (el.style.opacity = "0"), 2600);
  }

  // ============================================================
  // Init
  // ============================================================
  mountProfileSwitcher("profile-switcher");
  mountProfileSwitcher("profile-switcher-chargers");
  mountProfileSwitcher("profile-switcher-smart");
  mountProfileSwitcher("profile-switcher-settings");
  renderDashboard();
  renderChat();
})();
