"""고객 편익 (D): 일반 시스템에어컨 vs 하이브리드 콘덴싱에어컨.

고객순편익 = 전기요금절감액 − 증발수비용  (냉방용 열비용은 고객에게 청구하지 않으므로 차감하지 않음)
"""
from __future__ import annotations

import pandas as pd

from .cooling import cooling_table
from .inputs import Inputs


def customer_benefit(inp: Inputs):
    ct = cooling_table(inp)
    pe, pe_note = inp.elec_price_eff()
    pw, pw_note = inp.water_price_eff()
    q = ct["냉방 생산량(MWh_cool)"].sum()
    en, eh = ct["일반 냉방 전력(MWh_e)"].sum(), ct["하이브리드 냉방 전력(MWh_e)"].sum()
    water = ct["증발수량(㎥)"].sum()
    elec_n, elec_h = en * 1000 * pe, eh * 1000 * pe
    water_cost = water * pw
    saving = elec_n - elec_h
    net = saving - water_cost
    table = pd.DataFrame([
        ["냉방 생산량 (MWh_cool)", q, q, 0.0],
        ["전력사용량 (MWh_e)", en, eh, en - eh],
        ["전기요금 (억원)", elec_n / 1e8, elec_h / 1e8, saving / 1e8],
        ["증발수량 (㎥)", 0.0, water, -water],
        ["수도비 (억원)", 0.0, water_cost / 1e8, -water_cost / 1e8],
        ["고객 순비용 (억원)", elec_n / 1e8, (elec_h + water_cost) / 1e8, net / 1e8],
    ], columns=["항목", "일반 시스템에어컨", "하이브리드 에어컨", "차이(편익 +)"])
    res = {
        "q": q, "elec_normal": en, "elec_hybrid": eh, "saving_mwh": en - eh, "water_m3": water,
        "elec_saving_won": saving, "water_cost_won": water_cost, "net_won": net,
        "net_per_hh_won": net / inp.households, "elec_price": pe, "water_price": pw,
        "elec_note": pe_note, "water_note": pw_note,
    }
    # 부분부하 증발수 보정 시나리오(사용자 입력 시에만)
    if inp.water_partload_factor is not None:
        w2 = water * inp.water_partload_factor
        res["scenario_partload"] = {"water_m3": w2, "water_cost_won": w2 * pw, "net_won": saving - w2 * pw}
    monthly = pd.DataFrame({
        "월": ct["월"],
        "일반 전력(MWh_e)": ct["일반 냉방 전력(MWh_e)"], "하이브리드 전력(MWh_e)": ct["하이브리드 냉방 전력(MWh_e)"],
        "전기료 절감(억원)": (ct["전력 절감량(MWh_e)"] * 1000 * pe) / 1e8,
        "증발수(㎥)": ct["증발수량(㎥)"], "수도비(억원)": ct["증발수량(㎥)"] * pw / 1e8,
        "순편익(억원)": (ct["전력 절감량(MWh_e)"] * 1000 * pe - ct["증발수량(㎥)"] * pw) / 1e8,
    })
    return table, res, monthly
