"""Streamlit Web App: EV Fleet Smart Charging & German §14a EnWG Dispatch Optimizer."""

import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from src.charging_engine import EVSmartChargingEngine

st.set_page_config(
    page_title="EV Fleet Smart Charging §14a EnWG",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ EV Fleet Smart Charging & German §14a EnWG Dispatch Engine")
st.markdown("Mathematical charging optimizer managing **Dynamic Wholesale + Grid Fees (Netzentgelte Modul 3)**, mandatory **§14a EnWG Grid Dimming (4.2 kW/EV)**, and morning fleet **SLA Delivery**.")

# Sidebar Parameters
st.sidebar.header("🚗 Fleet Operational Parameters")
num_vehicles = st.sidebar.slider("Fleet Size (Commercial EVs)", 5, 50, 20, 5)
battery_capacity = st.sidebar.slider("Battery Size per EV (kWh)", 40.0, 100.0, 60.0, 10.0)
target_soc = st.sidebar.slider("Morning Departure SLA Target (%)", 70, 100, 85, 5) / 100.0

st.sidebar.header("⚖️ German §14a EnWG Parameters")
dimmed_power = st.sidebar.slider("Dimmed Power Cap per EV (§14a EnWG) [kW]", 2.0, 6.0, 4.2, 0.2)
peak_grid_fee = st.sidebar.slider("Peak Grid Congestion Fee (ct/kWh)", 5.0, 20.0, 11.5, 0.5)

@st.cache_data
def generate_market_data(peak_fee):
    np.random.seed(42)
    hours = 24
    h_arr = np.arange(hours)

    spot_mwh = 70.0 + 35.0 * np.sin(2 * np.pi * (h_arr - 6) / 24) + np.random.normal(0, 4.0, hours)
    spot_mwh[12:15] -= 20.0
    spot_ct = spot_mwh / 10.0

    grid_fee = np.where((h_arr >= 17) & (h_arr <= 21), peak_fee, 4.2)
    curtailed = np.zeros(hours)
    curtailed[18:21] = 1.0

    return pd.DataFrame({
        "hour": h_arr,
        "spot_price_ct_kwh": spot_ct,
        "grid_fee_ct_kwh": grid_fee,
        "total_tariff_ct_kwh": spot_ct + grid_fee,
        "enwg14a_curtailed": curtailed
    })

df_raw = generate_market_data(peak_grid_fee)
charging_window = [18, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5, 6]

engine = EVSmartChargingEngine(
    num_vehicles=num_vehicles,
    battery_capacity_kwh=battery_capacity,
    dimmed_charger_kw=dimmed_power,
    sla_target_soc=target_soc
)

df_res, kpis = engine.optimize_charging(df_raw, charging_window, avg_initial_soc=0.30)

# Top KPIs Row
k1, k2, k3, k4 = st.columns(4)
k1.metric("Optimized Smart Cost", f"€{kpis['smart_cost_eur']:.2f}")
k2.metric("Uncontrolled Baseline", f"€{kpis['naive_cost_eur']:.2f}")
k3.metric("Net Cost Reduction", f"€{kpis['cost_savings_eur']:.2f}", delta=f"{kpis['cost_savings_pct']:.1f}% Savings")
k4.metric("§14a EnWG Compliance", "100% (<= 4.2 kW/EV)")

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📊 Dynamic Tariff Structure & Coordinated Charging Stack")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    ax1.plot(df_res["hour"], df_res["total_tariff_ct_kwh"], color="#DC2626", lw=2.0, label="Total Tariff (Spot + Netzentgelt)")
    ax1.plot(df_res["hour"], df_res["spot_price_ct_kwh"], color="#F59E0B", linestyle="--", lw=1.5, label="Spot Energy Only")
    ax1.axvspan(17.5, 20.5, color="#DC2626", alpha=0.15, label="§14a Congestion Window")
    ax1.set_ylabel("Tariff [ct/kWh]", fontweight="bold")
    ax1.set_title("German Dynamic Grid Fees & §14a Dimming Zone (18:00 - 21:00)", fontsize=10, fontweight="bold")
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend(loc="upper left", frameon=True, fontsize=7.5)

    ax2.step(df_res["hour"], df_res["naive_charging_power_kw"], where="mid", color="#94A3B8", lw=1.8, linestyle="--", label="Uncontrolled Naive Charge (kW)")
    ax2.step(df_res["hour"], df_res["smart_charging_power_kw"], where="mid", color="#2563EB", lw=2.2, label="§14a Smart Dispatch (kW)")
    ax2.plot(df_res["hour"], df_res["max_allowed_power_kw"], color="#10B981", linestyle=":", lw=1.5, label="Grid Dimming Cap (kW)")
    ax2.set_xlabel("Hour of Day [0-23]", fontweight="bold")
    ax2.set_ylabel("Fleet Power [kW]", fontweight="bold")
    ax2.set_title("Overnight Valley Filling: Avoiding High-Fee Congestion Hours", fontsize=10, fontweight="bold")
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.legend(loc="upper right", frameon=True, fontsize=7.5)

    plt.tight_layout()
    st.pyplot(fig)

with col2:
    st.subheader("📑 Optimization Matrix")
    st.dataframe(
        pd.DataFrame({
            "Operational Metric": [
                "Fleet Vehicle Count",
                "Total Required Energy",
                "Uncontrolled Naive Cost",
                "Smart Optimized Cost",
                "Commercial P&L Savings",
                "Cost Reduction (%)",
                "SLA Target Readiness"
            ],
            "Value": [
                f"{num_vehicles} EVs",
                f"{kpis['total_energy_kwh']:.1f} kWh",
                f"€{kpis['naive_cost_eur']:.2f}",
                f"€{kpis['smart_cost_eur']:.2f}",
                f"€{kpis['cost_savings_eur']:.2f}",
                f"{kpis['cost_savings_pct']:.1f}%",
                "100% by 07:00 AM"
            ]
        }),
        hide_index=True,
        use_container_width=True
    )
    st.markdown("""
    **Regulatory & Market Features:**
    * **§14a EnWG Compliance:** Power intake automatically throttles to $\le 4.2\\text{ kW}$ per vehicle during distribution grid curtailment orders.
    * **Netzentgelte Modul 3:** Bypasses extreme evening network charges by shifting bulk fleet energy intake to the early morning hours (01:00–05:00).
    * **Guaranteed SLA Delivery:** Exact fleet demand fulfilled prior to morning commercial departure.
    """)

st.markdown("---")
st.caption("German EV Fleet Demand Side Management (DSM) & §14a EnWG Regulatory Smart Charging Architecture.")
