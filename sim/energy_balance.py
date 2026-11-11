"""월별 열 수요 환산 및 Energy Balance (B)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .constants import GJ_PER_MWH, MCAL_PER_MWH, MONTH_LABELS, PRIORITY
from .cooling import cooling_heat_demand_mwh
from .inputs import Inputs


def demand_table(inp: Inputs) -> pd.DataFrame:
    """130세대 실측 → 1,000세대 환산. Mcal / GJ / MWh_th 병기."""
    h = np.array(inp.heating_130, float) * inp.heating_factor      # Mcal
    d = np.array(inp.dhw_130, float) * inp.dhw_factor              # Mcal
    c = cooling_heat_demand_mwh(inp)                               # MWh_th
    return pd.DataFrame({
        "월": MONTH_LABELS,
        "난방 실측130(Mcal)": inp.heating_130,
        "급탕 실측130(Mcal)": inp.dhw_130,
        "난방(Mcal)": h, "급탕(Mcal)": d,
        "난방(GJ)": h / MCAL_PER_MWH * GJ_PER_MWH, "급탕(GJ)": d / MCAL_PER_MWH * GJ_PER_MWH,
        "난방(MWh_th)": h / MCAL_PER_MWH, "급탕(MWh_th)": d / MCAL_PER_MWH,
        "냉방용 열(MWh_th)": c,
    })


def energy_balance(inp: Inputs, n: int) -> pd.DataFrame:
    """연료전지 n대 기준 월별 열수지. 모든 열량 MWh_th, 전력 MWh_e."""
    L = inp.pipe_loss or 0.0                       # 미입력이면 미적용(0)으로 계산 → 미입력 목록에서 경고
    dt = demand_table(inp)
    heat_d, dhw_d, cool_d = dt["난방(MWh_th)"].to_numpy(), dt["급탕(MWh_th)"].to_numpy(), dt["냉방용 열(MWh_th)"].to_numpy()
    hrs = np.array(inp.hours, float)
    gen_h = inp.fc_heat_kw * hrs * inp.fc_util * n / 1000.0       # MWh_th
    gen_e = inp.fc_elec_kw * hrs * inp.fc_util * n / 1000.0       # MWh_e
    gas_mj = inp.fc_gas_mj_h * hrs * inp.fc_util * n               # MJ

    rows = []
    for i in range(12):
        season = inp.season_map[i]
        dem = {"dhw": dhw_d[i], "heat": heat_d[i], "cool": cool_d[i]}
        rem, used, src = gen_h[i], {}, 0.0
        for k in PRIORITY[season]:
            need_src = dem[k] / (1 - L)            # 배관손실 반영 시 FC측 필요열
            a = min(rem, need_src)
            used[k] = a * (1 - L)                  # 고객측 공급열
            rem -= a
            src += a
        tot_d = heat_d[i] + dhw_d[i] + cool_d[i]
        tot_used = sum(used.values())
        rows.append({
            "월": MONTH_LABELS[i], "계절": season, "월시간(h)": hrs[i],
            "난방열": heat_d[i], "급탕열": dhw_d[i], "냉방용 열": cool_d[i], "총 열수요": tot_d,
            "FC 발생열": gen_h[i],
            "난방 사용열": used["heat"], "급탕 사용열": used["dhw"], "냉방 사용열": used["cool"],
            "실제 사용열(공급열)": tot_used, "배관손실열": src - tot_used,
            "잉여열": max(rem, 0.0), "부족열": max(tot_d - tot_used, 0.0),
            "열자가소비율": tot_used / gen_h[i] if gen_h[i] else np.nan,
            "열폐기율": max(rem, 0.0) / gen_h[i] if gen_h[i] else np.nan,
            "열부하충족률": tot_used / tot_d if tot_d else np.nan,
            "전력 발전량(MWh_e)": gen_e[i], "가스 소비량(GJ)": gas_mj[i] / 1000.0, "가스 소비열량(MJ)": gas_mj[i],
        })
    return pd.DataFrame(rows)


def annual_row(bal: pd.DataFrame) -> dict:
    s = bal.sum(numeric_only=True)
    gen, used, tot = s["FC 발생열"], s["실제 사용열(공급열)"], s["총 열수요"]
    return {
        "FC 발생열": gen, "총 열수요": tot, "실제 사용열": used, "잉여열": s["잉여열"], "부족열": s["부족열"],
        "열자가소비율": used / gen if gen else np.nan,
        "열폐기율": s["잉여열"] / gen if gen else np.nan,
        "열부하충족률": used / tot if tot else np.nan,
    }
