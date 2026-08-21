"""
Smart EV Fleet Charging & German §14a EnWG Regulatory Dispatch Engine.
Optimizes fleet charging schedules under dynamic spot + grid tariffs, dimming orders, and arrival/departure SLAs.
"""

from typing import Dict, Tuple, List
import numpy as np
import pandas as pd
from scipy.optimize import linprog


class EVSmartChargingEngine:

  def __init__(
      self,
      num_vehicles: int = 20,
      battery_capacity_kwh: float = 60.0,
      charger_efficiency: float = 0.92,
      standard_charger_kw: float = 11.0,
      dimmed_charger_kw: float = 4.2,
      sla_target_soc: float = 0.85,
  ):
    self.num_vehicles = num_vehicles
    self.battery_capacity_kwh = battery_capacity_kwh
    self.charger_efficiency = charger_efficiency
    self.standard_charger_kw = standard_charger_kw
    self.dimmed_charger_kw = dimmed_charger_kw
    self.sla_target_soc = sla_target_soc

  def optimize_charging(
      self,
      df_market: pd.DataFrame,
      charging_hours: List[int],
      avg_initial_soc: float = 0.30,
  ) -> Tuple[pd.DataFrame, Dict[str, float]]:
    df = df_market.copy()
    hours = len(df)

    # 1. Energy Calculation & Fleet SLA Targets
    initial_soc_kwh = avg_initial_soc * self.battery_capacity_kwh
    target_soc_kwh = self.sla_target_soc * self.battery_capacity_kwh
    energy_per_ev = target_soc_kwh - initial_soc_kwh
    total_fleet_energy_needed = self.num_vehicles * energy_per_ev

    # 2. Dynamic Capacity Limits with §14a EnWG Dimming Orders
    max_fleet_power_kw = np.zeros(hours)
    for t in range(hours):
      if t in charging_hours:
        if df.loc[t, "enwg14a_curtailed"] == 1.0:
          max_fleet_power_kw[t] = self.num_vehicles * self.dimmed_charger_kw
        else:
          max_fleet_power_kw[t] = self.num_vehicles * self.standard_charger_kw
      else:
        max_fleet_power_kw[t] = 0.0

    df["max_allowed_power_kw"] = max_fleet_power_kw

    # 3. Linear Programming (HiGHS Solver)
    c = df["total_tariff_ct_kwh"].values

    A_eq = np.zeros((1, hours))
    for t in charging_hours:
      A_eq[0, t] = self.charger_efficiency
    b_eq = np.array([total_fleet_energy_needed])

    bounds = [(0.0, max_fleet_power_kw[t]) for t in range(hours)]

    res = linprog(c, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if not res.success:
      raise RuntimeError(f"Smart Charging Optimization Failed: {res.message}")

    p_smart_kw = res.x
    df["smart_charging_power_kw"] = p_smart_kw

    # 4. Naive Uncontrolled Baseline
    p_naive_kw = np.zeros(hours)
    energy_delivered_naive = 0.0
    for t in charging_hours:
      rem = total_fleet_energy_needed - energy_delivered_naive
      if rem <= 0:
        break
      p = min(max_fleet_power_kw[t], rem / self.charger_efficiency)
      p_naive_kw[t] = p
      energy_delivered_naive += p * self.charger_efficiency

    df["naive_charging_power_kw"] = p_naive_kw

    # 5. Financial & Operational KPIs
    tariffs_eur_kwh = df["total_tariff_ct_kwh"].values / 100.0
    cost_smart = float(np.sum(p_smart_kw * tariffs_eur_kwh))
    cost_naive = float(np.sum(p_naive_kw * tariffs_eur_kwh))
    savings_eur = cost_naive - cost_smart
    savings_pct = (savings_eur / cost_naive) * 100.0 if cost_naive > 0 else 0.0

    curtailed_energy_avoided = float(
        np.sum(
            p_smart_kw[df["enwg14a_curtailed"] == 1.0]
        )
    )

    kpis = {
        "total_energy_kwh": round(total_fleet_energy_needed, 1),
        "naive_cost_eur": round(cost_naive, 2),
        "smart_cost_eur": round(cost_smart, 2),
        "cost_savings_eur": round(savings_eur, 2),
        "cost_savings_pct": round(savings_pct, 1),
        "smart_curtailed_window_draw_kwh": round(curtailed_energy_avoided, 1),
    }

    return df, kpis
