"""종합효율 검증 (F): η_total = (발전전력 + 실제 사용열) / 투입가스열 ≥ 60%."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .constants import MJ_PER_KWH
from .inputs import Inputs

THRESHOLD = 0.60


def efficiency_table(inp: Inputs, bal: pd.DataFrame) -> pd.DataFrame:
    gas = bal["가스 소비열량(MJ)"].to_numpy()
    e_mj = bal["전력 발전량(MWh_e)"].to_numpy() * 1000 * MJ_PER_KWH
    h_mj = bal["실제 사용열(공급열)"].to_numpy() * 1000 * MJ_PER_KWH
    rows = []
    for i in range(len(bal)):
        eta_e, eta_h = e_mj[i] / gas[i], h_mj[i] / gas[i]
        rows.append(_row(bal.loc[i, "월"], gas[i], e_mj[i], h_mj[i], bal.loc[i]))
    rows.append(_row("연간", gas.sum(), e_mj.sum(), h_mj.sum(), bal.sum(numeric_only=True)))
    return pd.DataFrame(rows)


def _row(label, gas, e_mj, h_mj, b):
    eta_e, eta_h = e_mj / gas, h_mj / gas
    eta = eta_e + eta_h
    ok = eta >= THRESHOLD
    cause = ""
    if not ok:
        gen = b["FC 발생열"]
        waste = b["잉여열"] / gen if gen else 0
        cause = (f"열수요 < 발생열로 잉여열 {b['잉여열']:,.0f} MWh_th(폐기율 {waste:.0%}) 발생 → "
                 f"유효열 감소 (총 열수요 {b['총 열수요']:,.0f} MWh_th)")
    return {"구분": label, "투입가스열(GJ)": gas / 1000, "발전전력(GJ)": e_mj / 1000, "실제 사용열(GJ)": h_mj / 1000,
            "전기효율": eta_e, "열회수효율": eta_h, "종합효율": eta, "60% 판정": "충족" if ok else "미충족", "미달 원인": cause}


def annual_total_efficiency(inp: Inputs, bal: pd.DataFrame) -> float:
    return float(efficiency_table(inp, bal).iloc[-1]["종합효율"])
