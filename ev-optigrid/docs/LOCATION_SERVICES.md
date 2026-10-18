# Location Services

## Provider abstraction (spec §2/§39)

Five interfaces (`backend/services/providers/base.py`), each with a Demo
implementation (`demo_providers.py`) and a factory (`factory.py`) that
picks real-vs-demo from environment variables — never hardcoded, never
scattered across the codebase:

| Interface | Demo implementation | Real provider slot |
|---|---|---|
| `LocationProvider` | Deterministic hash-based geocoding | Google/Mapbox geocoding |
| `RoutingProvider` | Haversine distance × 1.35 road-network factor | OSRM / Mapbox / Google Directions |
| `ChargingStationProvider` | Deterministic synthetic stations around a point | Open Charge Map / a live station network API |
| `WeatherProvider` | Deterministic synthetic temperature/condition | OpenWeather |
| `LLMProvider` | Fixed acknowledgement string | Anthropic/OpenAI API |

**No API keys ever reach the frontend.** All provider calls happen
server-side in `backend/services/`; the frontend only ever calls this
project's own `/api/...` endpoints.

## DEMO MODE (spec §29/§30)

If a provider's API key isn't configured (`backend/.env`), the factory
returns its Demo implementation automatically — the whole platform stays
usable and demoable with zero external accounts. Every object a provider
returns carries a `source` field (`"real"` or `"demo"`), and every
`StationCardSchema`/route response surfaces it — the UI is expected to
render a visible badge rather than let simulated data pass as live (spec
§29: "Never present simulated charger availability as live real-world
availability").

`backend/services/providers/factory.py` deliberately does NOT silently
fall back to Demo when a *real* provider is misconfigured (a name set but
implementation missing) — it raises `NotImplementedError` instead, so a
half-configured production deployment fails loudly rather than quietly
serving synthetic data under a "real" label.

## Location resolution flow

1. Frontend requests browser geolocation. Granted → `{lat, lng}` sent to
   the backend directly, no provider call needed for "current location".
2. Denied, or the user wants a different location → manual entry, which
   calls `LocationProvider.geocode(query)`.
3. Destination is always manual entry (or map pick) → same `geocode` call.
4. Nearby search: `ChargingStationProvider.find_nearby(location, radius_km)`.
5. Route + along-route search: `RoutingProvider.get_route(origin, dest)`
   then `ChargingStationProvider.find_along_route(route, corridor_km)`.

## Demo provider determinism

Both `DemoLocationProvider.geocode` and `DemoChargingStationProvider`
hash their input into a seed (`_seed_from_string`, SHA-256-based) rather
than using randomness — the same query or location always produces the
same result. This matters for two reasons: demos are reproducible run to
run, and `tests/backend/test_providers_and_journey.py` can assert
determinism directly rather than only checking "is a plausible-looking
result returned."

## What a real provider integration would change

Only `backend/services/providers/factory.py` and one new file (e.g.
`real_providers.py` implementing the same five interfaces against a real
API). No changes needed in `station_service.py`, `journey_service.py`,
the optimization pipeline, or any router — they depend on the interface
types (`RouteResult`, `StationInfo`, ...), never on which concrete class
produced them.
