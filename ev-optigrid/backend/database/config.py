"""
Centralized application settings.

All external-provider selection (maps/routing/stations/weather/LLM) is read
here from environment variables and nowhere else — services must depend on
`get_settings()` rather than reading os.environ directly, so provider choice
stays swappable and testable (see docs/LOCATION_SERVICES.md).
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_JWT_SECRET = "dev_secret_change_me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "sqlite:///./evoptigrid.db"

    # Auth
    jwt_secret_key: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Providers — each defaults to "demo" so the app is runnable with zero keys
    routing_provider: str = "demo"
    routing_provider_api_key: str | None = None

    station_provider: str = "demo"
    station_provider_api_key: str | None = None

    weather_provider: str = "demo"
    weather_provider_api_key: str | None = None

    llm_provider: str = "demo"
    llm_provider_api_key: str | None = None

    # App
    environment: str = "development"
    cors_origins: str = "http://localhost:3000"
    rate_limit_per_minute: int = 120
    enable_scheduler: bool = True     # background model warm-up (services/scheduler.py)

    def assert_safe_for_environment(self) -> None:
        """Refuse to start outside development with the well-known default JWT secret."""
        if self.environment != "development" and self.jwt_secret_key == DEFAULT_JWT_SECRET:
            raise RuntimeError(
                "JWT_SECRET_KEY is still the built-in development default. Set a long random value "
                "(e.g. `python -c \"import secrets; print(secrets.token_urlsafe(48))\"`) before running "
                f"with ENVIRONMENT={self.environment!r}.")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_demo_mode(self) -> bool:
        """True if NO real external provider is configured at all."""
        return all(
            p == "demo"
            for p in (
                self.routing_provider,
                self.station_provider,
                self.weather_provider,
                self.llm_provider,
            )
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
