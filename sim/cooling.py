"""냉방부하 / 냉방열 / 전력 / 증발수 계산 (A-3, A-4)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .constants import MONTH_LABELS
from .inputs import Inputs


def peak_kw_per_household(inp: Inputs) -> float:
    f = inp.sw_ratio * inp.sw_factor + (1 - inp.sw_ratio) * inp.se_factor
    return inp.cool_w_per_m2 * inp.cool_area_m2 * f / 1000.0


def peak_mw_total(inp: Inputs) -> float:
    return peak_kw_per_household(inp) * inp.households / 1000.0


def water_l_per_kwh_cool(inp: Inputs) -> float:
    return inp.water_lpm * 60.0 / inp.hyb_cool_kw


def cooling_table(inp: Inputs) -> pd.DataFrame:
    P = peak_mw_total(inp)                       # MW_cool
    h = np.array(inp.heflh, float)
    q = P * h                                    # MWh_cool
    return pd.DataFrame({
        "월": MONTH_LABELS,
        "등가전부하시간(h)": h,
        "냉방 생산량(MWh_cool)": q,
        "일반 냉방 전력(MWh_e)": q / inp.cop_normal,
        "하이브리드 냉방 전력(MWh_e)": q / inp.cop_hyb_e,
        "전력 절감량(MWh_e)": q / inp.cop_normal - q / inp.cop_hyb_e,
        "냉방용 필요 열(MWh_th)": q / inp.cop_hyb_h,
        "증발수량(㎥)": q * water_l_per_kwh_cool(inp),   # MWh×1000kWh×L/kWh÷1000
    })


def cooling_heat_demand_mwh(inp: Inputs) -> np.ndarray:
    return cooling_table(inp)["냉방용 필요 열(MWh_th)"].to_numpy()
