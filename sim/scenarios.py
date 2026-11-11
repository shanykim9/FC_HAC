"""연료전지 대수별 비교 및 적정 대수 추천 (A-5, H)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .economics import run_economics
from .efficiency import THRESHOLD, annual_total_efficiency
from .energy_balance import annual_row
from .inputs import Inputs


def sweep(inp: Inputs):
    """N=1..n_max 비교표와 대수별 상세 결과(dict)."""
    rows, details = [], {}
    ref_rate = inp.discount_rate if inp.discount_rate is not None else inp.target_irr
    for n in range(1, int(inp.n_max) + 1):
        res = run_economics(inp, n)
        details[n] = res
        a = annual_row(res["bal"])
        eta = annual_total_efficiency(inp, res["bal"])
        sidx = [i for i in range(12) if inp.season_map[i] == "하절기"]
        s_gen = float(res["bal"].loc[sidx, "FC 발생열"].sum())
        s_dem = float(res["bal"].loc[sidx, "총 열수요"].sum())
        s_sur = float(res["bal"].loc[sidx, "잉여열"].sum())
        row = {"대수": n, "하절기 FC 발생열(MWh_th)": s_gen, "하절기 총 열부하(MWh_th)": s_dem, "하절기 잉여열(MWh_th)": s_sur,
               "하절기 조건 충족": "충족" if (sidx and s_gen <= s_dem * (1 + inp.summer_surplus_tol) + 1e-9) else "초과", "FC 발생열(MWh_th)": a["FC 발생열"], "총 열수요(MWh_th)": a["총 열수요"],
               "실제 사용열(MWh_th)": a["실제 사용열"], "잉여열(MWh_th)": a["잉여열"], "부족열(MWh_th)": a["부족열"],
               "열자가소비율": a["열자가소비율"], "열폐기율": a["열폐기율"], "열부하충족률": a["열부하충족률"],
               "종합효율": eta, "60% 충족": "충족" if eta >= THRESHOLD else "미충족"}
        if res["status"] == "hold" or res.get("m_pre") is None:
            row.update({"IRR(HPS 전)": np.nan, "NPV(HPS 전, 억원)": np.nan, "필요 HPS(억원/년)": np.nan, "필요 HPS(원/kWh)": np.nan})
        else:
            cf = res["cf_pre"]
            net = cf["순현금흐름"].to_numpy()
            npv_ref = float(np.sum(net / (1 + ref_rate) ** np.arange(len(net))))
            row.update({"IRR(HPS 전)": res["m_pre"]["irr"], "NPV(HPS 전, 억원)": npv_ref / 1e8,
                        "필요 HPS(억원/년)": (res["hps"] or {}).get("H", np.nan) / 1e8 if res.get("hps") and res["hps"].get("H") is not None else np.nan,
                        "필요 HPS(원/kWh)": (res["hps"] or {}).get("h", np.nan) if res.get("hps") and res["hps"].get("h") is not None else np.nan})
        rows.append(row)
    df = pd.DataFrame(rows)
    df.attrs["npv_rate"] = ref_rate
    df.attrs["npv_rate_is_ref"] = inp.discount_rate is not None
    return df, details


def recommend(inp: Inputs, df: pd.DataFrame):
    """대수 선정 기준: 연료전지 열 발생량이 하절기 총 열부하(냉방+급탕+난방)를 넘지 않는 최대 대수.
    하절기에 열이 남지 않게 하는 것이 기본이며, 허용 잉여 비율(축열조 저장분)을 입력하면 그만큼 완화.
    NPV·IRR은 표에 함께 표시하되 선정 기준에는 사용하지 않는다."""
    ok = df[df["하절기 조건 충족"] == "충족"]
    tol = inp.summer_surplus_tol
    if len(ok):
        n = int(ok["대수"].max())
        r = df[df["대수"] == n].iloc[0]
        why = (f"하절기 FC 발생열 {r['하절기 FC 발생열(MWh_th)']:,.0f} MWh_th ≤ 하절기 총 열부하 {r['하절기 총 열부하(MWh_th)']:,.0f} MWh_th"
               f"{f' (허용 잉여 {tol:.0%} 적용)' if tol else ''} 를 만족하는 최대 대수"
               + (" — 비교 범위 상한이라 더 큰 대수도 가능할 수 있음" if n == int(df['대수'].max()) else ""))
    else:
        n = 1
        why = "1대도 하절기 총 열부하를 초과 — 최소 1대로 두되 하절기 잉여열은 축열조 저장 또는 부하 재검토 필요"
    eff_ok = df[df["60% 충족"] == "충족"]
    n_eff = int(eff_ok["대수"].max()) if len(eff_ok) else None   # 참고: 종합효율 60% 유지 최대 대수
    return n, why, n_eff
