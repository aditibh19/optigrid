from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from database.config import get_settings
from database.session import get_db

settings = get_settings()
settings.assert_safe_for_environment()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    from services import scheduler
    scheduler.start_scheduler(enabled=settings.enable_scheduler)
    yield
    scheduler.stop_scheduler()


app = FastAPI(
    lifespan=lifespan,
    title="EV-OptiGrid API",
    description="AI-powered personalized EV charging, route and energy optimization platform.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    from services import scheduler
    return {"status": "ok", "environment": settings.environment, "demo_mode": settings.is_demo_mode,
            "scheduler": scheduler.status()}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


# Routers, wired up as each service comes online:
from api import charging, stations, journeys, copilot, auth, vehicles, predictions, simulation, analysis, twin, fleet, battery
from api.deps import get_current_user

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(vehicles.router, prefix="/api/vehicles", tags=["vehicles"])
app.include_router(charging.router, prefix="/api/charging", tags=["charging"])
app.include_router(stations.router, prefix="/api/stations", tags=["stations"])
app.include_router(journeys.router, prefix="/api/journeys", tags=["journeys"])
app.include_router(copilot.router, prefix="/api/copilot", tags=["copilot"])
app.include_router(predictions.router, prefix="/api/predictions", tags=["predictions"])
app.include_router(simulation.router, prefix="/api/simulation", tags=["simulation"],
                   dependencies=[Depends(get_current_user)])   # heavy compute: login required

_login_required = [Depends(get_current_user)]
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"], dependencies=_login_required)
app.include_router(twin.router, prefix="/api/twin", tags=["digital twin"], dependencies=_login_required)
app.include_router(fleet.router, prefix="/api/fleet", tags=["fleet"], dependencies=_login_required)
app.include_router(battery.router, prefix="/api/battery", tags=["battery"], dependencies=_login_required)
