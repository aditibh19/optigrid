"""
Provider factory (Phase 10, spec §39).

The ONLY place in the codebase that should import both a provider interface
and its concrete implementations. Every service asks this factory for a
provider rather than constructing one directly, so adding a real provider
later (e.g. `MapboxRoutingProvider`) means writing that one class and
adding one branch here — nothing else in the codebase changes.
"""
from database.config import get_settings
from services.providers.base import (
    LocationProvider, RoutingProvider, ChargingStationProvider, WeatherProvider, LLMProvider,
)
from services.providers.demo_providers import (
    DemoLocationProvider, DemoRoutingProvider, DemoChargingStationProvider,
    DemoWeatherProvider, DemoLLMProvider,
)


def get_location_provider() -> LocationProvider:
    # No real geocoding provider wired yet in this build — always demo for
    # now; the branch below is where e.g. a Google/Mapbox geocoder plugs in.
    return DemoLocationProvider()


def get_routing_provider() -> RoutingProvider:
    settings = get_settings()
    if settings.routing_provider == "demo" or not settings.routing_provider_api_key:
        return DemoRoutingProvider()
    # Real provider(s) plug in here, keyed by settings.routing_provider
    # ("mapbox" | "osrm" | "google"), e.g.:
    #   if settings.routing_provider == "mapbox":
    #       return MapboxRoutingProvider(api_key=settings.routing_provider_api_key)
    raise NotImplementedError(
        f"Routing provider '{settings.routing_provider}' is configured but not yet implemented "
        f"— falling back is intentionally NOT automatic here so misconfiguration is loud, not silent."
    )


def get_station_provider() -> ChargingStationProvider:
    settings = get_settings()
    if settings.station_provider == "demo" or not settings.station_provider_api_key:
        return DemoChargingStationProvider()
    raise NotImplementedError(
        f"Station provider '{settings.station_provider}' is configured but not yet implemented."
    )


def get_weather_provider() -> WeatherProvider:
    settings = get_settings()
    if settings.weather_provider == "demo" or not settings.weather_provider_api_key:
        return DemoWeatherProvider()
    raise NotImplementedError(
        f"Weather provider '{settings.weather_provider}' is configured but not yet implemented."
    )


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "demo" or not settings.llm_provider_api_key:
        return DemoLLMProvider()
    raise NotImplementedError(
        f"LLM provider '{settings.llm_provider}' is configured but not yet implemented."
    )
