"""기존 검토 결과와의 대조 검증 (A-3, A-4, A-6, D)."""
from __future__ import annotations

import pandas as pd

from .constants import REFERENCE_CHECKS
from .customer import customer_benefit
from .cooling import cooling_table
from .fuelcell import gas_cost_annual
from .inputs import Inputs


def validate(inp: Inputs) -> pd.DataFrame:
    ct = cooling_table(inp)
    _, cb, _ = customer_benefit(inp)
    Y = inp.analysis_years
    # 기존 검토값은 부가세 처리 전 입력단가(25.0573원/MJ) 기준 → 입력단가 그대로 비교
    raw = lambda n: inp.fc_gas_mj_h * inp.gas_price * inp.hours_year * inp.fc_util * n / 1e8
    g1, g2 = raw(1), raw(2)
    calc = {
        "cool_total": ct["냉방 생산량(MWh_cool)"].sum(), "normal_elec": cb["elec_normal"],
        "hybrid_elec": cb["elec_hybrid"], "saving": cb["saving_mwh"], "heat": ct["냉방용 필요 열(MWh_th)"].sum(),
        "water": cb["water_m3"], "gas_1y": g1, "gas_1_20": g1 * 20, "gas_2y": g2, "gas_2_20": g2 * 20,
        "elec_save": cb["elec_saving_won"] / 1e8, "water_cost": cb["water_cost_won"] / 1e8,
        "net": cb["net_won"] / 1e8, "net_hh": cb["net_per_hh_won"] / 1e4,
    }
    rows = []
    for k, (name, ref, dec, unit) in REFERENCE_CHECKS.items():
        v = calc[k]
        tol = max(0.5 * 10 ** (-dec), 0.01 * abs(ref))
        ok = abs(v - ref) <= tol + 1e-9
        if k == "normal_elec":                      # 기준: 772~773
            ok = 771.5 <= v <= 773.5
        rows.append({"항목": name, "계산값": v, "기존 검토 기준": ref, "단위": unit, "차이": v - ref,
                     "판정": "일치" if ok else "불일치(입력값 변경 영향 가능)"})
    return pd.DataFrame(rows)
