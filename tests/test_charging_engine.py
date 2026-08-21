"""Automated Pytest Suite for EV Fleet Smart Charging Engine."""

import pytest
import numpy as np
import pandas as pd
from src.charging_engine import EVSmartChargingEngine


@pytest.fixture
def sample_24h_charging_data():
  hours = 24
  h = np.arange(hours)
  spot_ct = 7.0 + 3.5 * np.sin(2 * np.pi * (h - 6) / 24)
  grid_fee = np.where((h >= 17) & (h <= 21), 11.5, 4.2)
  curtailed = np.zeros(hours)
  curtailed[18:21] = 1.0  # §14a Dimming Active

  return pd.DataFrame({
      "hour": h,
      "spot_price_ct_kwh": spot_ct,
      "grid_fee_ct_kwh": grid_fee,
      "total_tariff_ct_kwh": spot_ct + grid_fee,
      "enwg14a_curtailed": curtailed,
  })


def test_enwg14a_dimming_and_savings(sample_24h_charging_data):
  engine = EVSmartChargingEngine(num_vehicles=10)
  charging_hours = [18, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5, 6]

  df_res, kpis = engine.optimize_charging(
      sample_24h_charging_data, charging_hours, avg_initial_soc=0.30
  )

  # Check that smart optimization never exceeds dimmed limits
  dimmed_limit = 10 * 4.2
  assert (
      df_res.loc[df_res["enwg14a_curtailed"] == 1.0, "smart_charging_power_kw"].max()
      <= dimmed_limit + 1e-5
  )

  # Check cost reduction
  assert kpis["cost_savings_eur"] > 0.0
  assert kpis["cost_savings_pct"] > 0.0

  # Check total energy delivered matches SLA exactly
  total_delivered = df_res["smart_charging_power_kw"].sum() * 0.92
  assert total_delivered == pytest.approx(kpis["total_energy_kwh"], 0.01)
