"""축열조 및 피크 대응 (G).

월별 총량만으로 용량을 확정하지 않는다. Peak-day 시간별 자료가 모두 있어야 계산하고,
없으면 '축열조 용량 산정 불가, 추가입력 필요'를 반환한다.
Q_storage = Σ max(Q_load,t − Q_FC,t, 0),   V = Q / (ρ·Cp·ΔT)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

RHO = 1000.0   # kg/㎥ (물, 물성상수)
CP = 4.186     # kJ/kg·K (물, 물성상수)


@dataclass
class StorageInputs:
    hourly: pd.DataFrame                    # 시각, 냉방부하(MWh_cool/h), 급탕부하(MWh_th/h), FC 공급열(MWh_th/h)
    supply_temp: Optional[float] = None     # ℃
    return_temp: Optional[float] = None     # ℃
    loss_ratio: Optional[float] = None      # 허용 열손실(비율)
    min_residual: Optional[float] = None    # MWh_th
    eta_charge: Optional[float] = None
    eta_discharge: Optional[float] = None
    target_hours: Optional[float] = None    # h
    cop_heat: float = 1.7                   # 냉방부하 → 열수요 환산(하이브리드 열 COP)


REQUIRED = {
    "supply_temp": "축열조 공급 가능 온도", "return_temp": "축열조 환수온도", "loss_ratio": "허용 열손실",
    "min_residual": "최소 잔여용량", "eta_charge": "충·방열효율(충열)", "eta_discharge": "충·방열효율(방열)",
    "target_hours": "목표 피크 대응시간",
}


def empty_hourly() -> pd.DataFrame:
    return pd.DataFrame({"시각": [f"{h:02d}:00" for h in range(24)],
                         "냉방부하(MWh_cool/h)": np.nan, "급탕부하(MWh_th/h)": np.nan, "FC 공급열(MWh_th/h)": np.nan})


def compute(si: StorageInputs) -> dict:
    missing = [lab for k, lab in REQUIRED.items() if getattr(si, k) is None]
    h = si.hourly
    for c, lab in [("냉방부하(MWh_cool/h)", "Peak-day 24시간 냉방부하"), ("급탕부하(MWh_th/h)", "Peak-day 급탕부하"),
                   ("FC 공급열(MWh_th/h)", "시간별 연료전지 공급열")]:
        if h[c].isna().any():
            missing.append(lab + " (24시간 전부)")
    if si.supply_temp is not None and si.return_temp is not None and si.supply_temp <= si.return_temp:
        missing.append("공급온도 > 환수온도 (현재 ΔT ≤ 0)")
    if missing:
        return {"ok": False, "message": "축열조 용량 산정 불가, 추가입력 필요", "missing": missing}

    load = h["냉방부하(MWh_cool/h)"].to_numpy() / si.cop_heat + h["급탕부하(MWh_th/h)"].to_numpy()
    fc = h["FC 공급열(MWh_th/h)"].to_numpy()
    deficit = np.maximum(load - fc, 0.0)
    surplus = np.maximum(fc - load, 0.0)
    q_storage = float(deficit.sum())
    T = int(max(1, round(si.target_hours)))
    q_peakT = float(max(deficit[i:i + T].sum() for i in range(0, 24 - T + 1))) if T <= 24 else float(deficit.sum())
    dT = si.supply_temp - si.return_temp
    q_design = q_storage / (si.eta_charge * si.eta_discharge) / (1 - si.loss_ratio) + si.min_residual
    mwh_to_m3 = 3.6e6 / (RHO * CP * dT)          # 1 MWh = 3.6e6 kJ
    direct = float(np.minimum(load, fc).sum())
    charge = min(float(surplus.sum()) * si.eta_charge, q_design)
    discharge = min(q_storage, charge * si.eta_discharge)
    return {
        "ok": True, "load_total": float(load.sum()), "direct": direct, "charge": charge, "discharge": discharge,
        "unmet": q_storage - discharge, "q_storage": q_storage, "q_peakT": q_peakT, "q_design": q_design,
        "volume_m3": q_design * mwh_to_m3, "volume_effective_m3": q_storage * mwh_to_m3, "dT": dT,
        "hourly": pd.DataFrame({"시각": h["시각"], "총 열부하(MWh_th/h)": load, "FC 공급열(MWh_th/h)": fc,
                                "직접 공급(MWh_th/h)": np.minimum(load, fc), "부족열(MWh_th/h)": deficit,
                                "잉여열(MWh_th/h)": surplus}),
    }
