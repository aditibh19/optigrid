"""
Trains and evaluates all 5 forecasters (Phase 8) and prints real,
held-out MAE/RMSE/R² for each — nothing here is fabricated (spec §10).

Run with: python ml/demo_forecasting.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml import price_forecaster, grid_forecaster, solar_forecaster, queue_predictor, demand_predictor


def main():
    print("=" * 70)
    print("EV-OptiGrid — ML forecasting layer verification (Phase 8)")
    print("=" * 70)
    print("All datasets below are SYNTHETIC (spec §10/§29) — generated with")
    print("a realistic seasonal pattern + noise, not real historical data.")
    print()

    print("[A] Electricity price forecaster")
    _, winner = price_forecaster.train()
    print(f"  -> best: {winner.model_name} (RMSE={winner.rmse})\n")

    print("[B] Grid load forecaster")
    _, winner = grid_forecaster.train()
    print(f"  -> best: {winner.model_name} (RMSE={winner.rmse})\n")

    print("[C] Trip energy-demand predictor")
    _, winner = demand_predictor.train()
    print(f"  -> best: {winner.model_name} (RMSE={winner.rmse})\n")

    print("[D] Solar generation forecaster")
    _, winner = solar_forecaster.train()
    print(f"  -> best: {winner.model_name} (RMSE={winner.rmse})\n")

    print("[E] Charger queue predictor")
    _, winner = queue_predictor.train()
    print(f"  -> best: {winner.model_name} (RMSE={winner.rmse})\n")

    print("-" * 70)
    print("Sanity-check predictions from the saved (best) models:")
    print("-" * 70)
    price = price_forecaster.predict(hour=19, weekday=2, recent_price=9.0, price_yesterday_same_time=12.5)
    print(f"  Predicted price at 7pm on a Wednesday: ₹{price:.2f}/kWh")

    grid = grid_forecaster.predict(hour=19, weekday=2, recent_load=70.0, load_yesterday_same_time=88.0)
    print(f"  Predicted grid load at 7pm on a Wednesday: {grid:.1f}%")

    solar = solar_forecaster.predict(hour=13, weekday=2, generation_yesterday_same_time=6.0)
    print(f"  Predicted solar generation at 1pm: {solar:.2f} kWh")

    solar_night = solar_forecaster.predict(hour=23, weekday=2, generation_yesterday_same_time=0.0)
    print(f"  Predicted solar generation at 11pm (should be ~0): {solar_night:.2f} kWh")

    queue = queue_predictor.predict_queue_and_wait(hour=18, weekday=2, station_capacity=4, station_popularity=1.2)
    print(f"  Predicted queue at a busy station, 6pm: {queue}")

    demand = demand_predictor.predict(distance_km=120, efficiency_kwh_per_km=0.17, traffic_multiplier=1.2)
    print(f"  Predicted energy for a 120km trip: {demand:.2f} kWh")

    print()
    print("=" * 70)
    print("All forecasters trained, evaluated, and sanity-checked.")
    print("=" * 70)


if __name__ == "__main__":
    main()
