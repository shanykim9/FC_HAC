"""연료전지 사업수지 구성요소 (C): 가스비, 매전, 매열, 운영비. 금액 단위 = 원."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .constants import MONTH_LABELS
from .inputs import OEM_PER_KWH, Inputs


def gas_cost_hourly(inp: Inputs) -> float:
    """C_gas,h = 3,798.2 MJ/h × 단가 (원/h, 1대)"""
    return inp.fc_gas_mj_h * inp.gas_price_eff()


def gas_cost_annual(inp: Inputs, n: int) -> float:
    """C_gas,y = C_gas,h × 8,760h × 95% × N"""
    return gas_cost_hourly(inp) * inp.hours_year * inp.fc_util * n


def gen_kwh_annual(inp: Inputs, n: int) -> float:
    """E_FC,y = 400kW × 8,760h × 95% × N"""
    return inp.fc_elec_kw * inp.hours_year * inp.fc_util * n


def opex_year1(inp: Inputs, n: int) -> dict:
    """1년차 운영비 항목(원/년). 미입력 항목은 None."""
    gen = gen_kwh_annual(inp, n)
    oem = None
    if inp.oem_value is not None:
        oem = inp.oem_value * gen if inp.oem_unit == OEM_PER_KWH else inp.oem_value * n
    aux = None
    if inp.aux_kw is not None and inp.aux_price is not None:
        aux = inp.aux_kw * n * inp.hours_year * inp.fc_util * inp.aux_price
    return {
        "O&M·LTSA": oem,
        "보조동력비": aux,
        "보험·제세공과금": None if inp.insurance is None else inp.insurance * n,
        "기타 운영비": inp.other_opex,
    }


def heat_sales(inp: Inputs, bal: pd.DataFrame) -> pd.DataFrame:
    """매열수익: 인정 계절의 난방·급탕 공급열만. 냉방용(무상)·잉여열은 항상 0원."""
    rows = []
    for i in range(12):
        season = inp.season_map[i]
        sale = season in inp.heat_sale_seasons
        qty = float(bal.loc[i, "난방 사용열"] + bal.loc[i, "급탕 사용열"]) if sale else 0.0
        p_dist = inp.heat_price_mwh(i)
        p_fc = inp.fc_heat_price_mwh(i)
        if not sale:
            rev = 0.0
        elif p_fc is None:
            rev = np.nan                       # 단가 미입력 → 수익 미산정
        else:
            rev = qty * p_fc
        rows.append({"월": MONTH_LABELS[i], "계절": season, "매열 인정": "예" if sale else "아니오",
                     "매열량(MWh_th)": qty,
                     "지역난방 열요금(원/MWh_th)": np.nan if p_dist is None else p_dist,
                     "FC 매열단가(원/MWh_th)": np.nan if p_fc is None else p_fc,
                     "매열수익(원)": rev})
    return pd.DataFrame(rows)


def monthly_business(inp: Inputs, n: int, bal: pd.DataFrame, hs: pd.DataFrame, price: float, hps_annual: float = 0.0) -> pd.DataFrame:
    """월별 사업수지(1년차 단가). 연 고정비는 운전시간 비율로 월 배분. 미입력은 NaN."""
    hrs = np.array(inp.hours, float)
    share = hrs / hrs.sum()
    gen = bal["전력 발전량(MWh_e)"].to_numpy()
    ox = opex_year1(inp, n)
    df = pd.DataFrame({
        "월": MONTH_LABELS,
        "가스 소비량(GJ)": bal["가스 소비량(GJ)"],
        "가스비(원)": bal["가스 소비열량(MJ)"] * inp.gas_price_eff(),
        "전력 매전량(MWh_e)": gen,
        "기본 매전수익(원)": gen * 1000 * price,
        "동절기 난방·급탕 매열수익(원)": hs["매열수익(원)"],
        "HPS 보상금(원)": hps_annual * gen / gen.sum() if gen.sum() else 0.0,
    })
    for k, v in ox.items():
        df[f"{k}(원)"] = np.nan if v is None else v * share
    df["스택 교체비(원)"] = np.nan if (inp.stack_interval is None or inp.stack_cost is None) else 0.0
    cost_cols = ["가스비(원)"] + [f"{k}(원)" for k in ox]
    rev = df["기본 매전수익(원)"] + df["동절기 난방·급탕 매열수익(원)"].fillna(0) + df["HPS 보상금(원)"]
    df["월 사업수지(원)"] = rev - df[cost_cols].fillna(0).sum(axis=1)
    return df
