"""
Optional ESP32 telemetry simulator (Phase 38, spec §38).

No physical hardware is assumed. This generates realistic-looking
(voltage, current, power, energy, status) readings for a simulated
charging session and can optionally publish them over MQTT if a broker is
configured — otherwise it just yields readings for the caller to log or
stream over a WebSocket. Every reading is labeled `source="simulated"`,
never presented as real hardware telemetry (spec §29).
"""
import time
import random
from dataclasses import dataclass, asdict


@dataclass
class TelemetryReading:
    timestamp: float
    voltage_v: float
    current_a: float
    power_kw: float
    cumulative_energy_kwh: float
    charging_status: str   # "charging" | "idle" | "fault"
    source: str = "simulated"


class SimulatedCharger:
    """
    Simulates one charger's telemetry stream during a session. Nominal
    voltage is held roughly constant (as a real AC/DC charger would
    regulate it); current is derived from the target power level with
    small realistic jitter.
    """

    def __init__(self, nominal_voltage_v: float = 400.0, target_power_kw: float = 7.4, seed: int = 0):
        self.nominal_voltage_v = nominal_voltage_v
        self.target_power_kw = target_power_kw
        self._rng = random.Random(seed)
        self._cumulative_energy_kwh = 0.0

    def read(self, dt_seconds: float = 1.0, status: str = "charging") -> TelemetryReading:
        if status != "charging":
            voltage = self.nominal_voltage_v * (1.0 + self._rng.uniform(-0.005, 0.005))
            current = 0.0
            power = 0.0
        else:
            voltage = self.nominal_voltage_v * (1.0 + self._rng.uniform(-0.01, 0.01))
            power = self.target_power_kw * (1.0 + self._rng.uniform(-0.03, 0.03))
            current = (power * 1000.0) / max(voltage, 1e-6)
            self._cumulative_energy_kwh += power * (dt_seconds / 3600.0)

        return TelemetryReading(
            timestamp=time.time(), voltage_v=round(voltage, 1), current_a=round(current, 2),
            power_kw=round(power, 3), cumulative_energy_kwh=round(self._cumulative_energy_kwh, 4),
            charging_status=status,
        )


def stream_session(duration_seconds: int, target_power_kw: float = 7.4, interval_seconds: float = 1.0, seed: int = 0):
    """Generator yielding one TelemetryReading per interval for a simulated charging session."""
    charger = SimulatedCharger(target_power_kw=target_power_kw, seed=seed)
    elapsed = 0.0
    while elapsed < duration_seconds:
        yield charger.read(dt_seconds=interval_seconds)
        elapsed += interval_seconds


def publish_to_mqtt(reading: TelemetryReading, topic: str, broker_host: str, broker_port: int = 1883) -> bool:
    """
    Publishes a reading to an MQTT broker if `paho-mqtt` is installed and a
    broker is reachable; returns False (never raises) if not, so the
    simulator degrades gracefully to local-only mode with no hardware/
    broker available.
    """
    try:
        import paho.mqtt.publish as mqtt_publish
        import json
        mqtt_publish.single(topic, payload=json.dumps(asdict(reading)), hostname=broker_host, port=broker_port)
        return True
    except Exception:
        return False
