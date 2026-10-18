import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, fetchMe, listVehicles, login, optimizeCharging } from "../services/api";
import { AUTH_EXPIRED_EVENT, clearTokens, getTokens, saveTokens } from "../services/auth";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const bearer = (init?: RequestInit) => (init?.headers as Record<string, string> | undefined)?.Authorization;

beforeEach(() => { clearTokens(); });
afterEach(() => { vi.unstubAllGlobals(); });

describe("authenticated requests", () => {
  it("sends the access token as a Bearer header", async () => {
    saveTokens({ access_token: "a1", refresh_token: "r1" });
    const fetchMock = vi.fn().mockResolvedValue(json(200, { id: "u", email: "e", name: "n" }));
    vi.stubGlobal("fetch", fetchMock);
    await fetchMe();
    expect(bearer(fetchMock.mock.calls[0][1])).toBe("Bearer a1");
  });

  it("sends no Authorization header when logged out", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(200, []));
    vi.stubGlobal("fetch", fetchMock);
    await listVehicles();
    expect(bearer(fetchMock.mock.calls[0][1])).toBeUndefined();
  });

  it("refreshes an expired access token once, then retries the original request", async () => {
    saveTokens({ access_token: "old", refresh_token: "r-old" });
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/auth/refresh") return json(200, { access_token: "new", refresh_token: "r-new", token_type: "bearer" });
      return bearer(init) === "Bearer new" ? json(200, { id: "u", email: "e", name: "n" }) : json(401, { detail: "expired" });
    });
    vi.stubGlobal("fetch", fetchMock);
    const me = await fetchMe();
    expect(me.id).toBe("u");
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual(["/api/auth/me", "/api/auth/refresh", "/api/auth/me"]);
    expect(getTokens()).toEqual({ access_token: "new", refresh_token: "r-new" });
  });

  it("shares ONE refresh between concurrent requests that all hit 401", async () => {
    saveTokens({ access_token: "old", refresh_token: "r-old" });
    let refreshes = 0;
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/auth/refresh") { refreshes++; await new Promise((r) => setTimeout(r, 20)); return json(200, { access_token: "new", refresh_token: "r-new", token_type: "bearer" }); }
      return bearer(init) === "Bearer new" ? json(200, url === "/api/vehicles" ? [] : { id: "u", email: "e", name: "n" }) : json(401, { detail: "expired" });
    }));
    await Promise.all([fetchMe(), listVehicles(), listVehicles()]);
    expect(refreshes).toBe(1);
  });

  it("clears the session and announces it when the refresh token is rejected", async () => {
    const events = new EventTarget();
    vi.stubGlobal("window", events);
    const expired = vi.fn();
    events.addEventListener(AUTH_EXPIRED_EVENT, expired);
    saveTokens({ access_token: "old", refresh_token: "bad" });
    vi.stubGlobal("fetch", vi.fn(async () => json(401, { detail: "nope" })));
    await expect(fetchMe()).rejects.toMatchObject({ status: 401 });
    expect(getTokens()).toBeNull();
    expect(expired).toHaveBeenCalledOnce();
  });

  it("does not try to refresh when the login itself is rejected", async () => {
    saveTokens({ access_token: "a", refresh_token: "r" });
    const fetchMock = vi.fn().mockResolvedValue(json(401, { detail: "Incorrect email or password." }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(login("a@b.com", "wrongwrong")).rejects.toThrow("Incorrect email or password.");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("error handling", () => {
  const body = { battery_capacity_kwh: 60, max_charge_rate_kw: 50, current_soc_pct: 150, target_soc_pct: 90, minimum_safe_soc_pct: 70,
    horizon_slots: 24, slot_minutes: 15, current_price_per_kwh: 8, current_grid_load_pct: 60, current_solar_availability_frac: 0.2, profile: "balanced" as const };

  it("turns FastAPI validation errors into one readable line", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(422, { detail: [{ loc: ["body", "current_soc_pct"], msg: "Input should be less than or equal to 100" }] })));
    await expect(optimizeCharging(body)).rejects.toThrow("current_soc_pct: Input should be less than or equal to 100");
  });

  it("uses the server's detail string when there is one", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(404, { detail: "Vehicle not found." })));
    await expect(fetchMe()).rejects.toMatchObject({ status: 404, message: "Vehicle not found." });
  });

  it("explains how to start the backend when it cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const err = await fetchMe().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
    expect(err.message).toMatch(/uvicorn/);
  });
});
