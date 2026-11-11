"""최종검토 리포트: 분석 조건·산출 근거, 최종 결론, 대수 비교, 추가 확인 사항을 한 곳에 정리.

모든 수치·문구는 현재 입력값과 계산 결과에서 파생한다(임의 수치 생성 금지).
반환: {"conditions": DF, "conclusion": DF, "units": DF, "extra": DF}  (Excel 시트로도 사용)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .constants import MCAL_PER_MWH
from .cooling import cooling_table, peak_kw_per_household, peak_mw_total, water_l_per_kwh_cool
from .efficiency import annual_total_efficiency
from .energy_balance import demand_table
from .fuelcell import gas_cost_annual, gas_cost_hourly, gen_kwh_annual
from .inputs import ELEC_S1, GAS_VAT_EXCL, GAS_VAT_INCL, Inputs


def _eok(x) -> str:
    return "산정 불가" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x / 1e8:,.2f}억원"


def _heat_price_text(inp: Inputs) -> str:
    idx = [i for i in range(12) if inp.season_map[i] in inp.heat_sale_seasons]
    prices = [inp.heat_price_mwh(i) for i in idx]
    if not idx or any(p is None for p in prices):
        return "매열 인정 계절의 지역난방 열요금 미입력 → 매열수익 미산정 (추가입력 필요)"
    pm = float(np.mean(prices))
    r = inp.fc_heat_price_ratio
    same = max(prices) - min(prices) < 1e-6
    lab = "동일" if same else "월 평균"
    return (f"지역난방 열요금({', '.join(inp.heat_sale_seasons)}) {pm / MCAL_PER_MWH:,.2f}원/Mcal ({pm / 1000:,.2f}원/kWh, {lab}) × {r:.0%} "
            f"= FC 매열단가 {pm * r / MCAL_PER_MWH:,.2f}원/Mcal ({pm * r / 1000:,.2f}원/kWh, {pm * r:,.0f}원/MWh_th)")


def build_report(inp: Inputs, n: int, res: dict, cb: dict, summary: dict, sweep_df: pd.DataFrame, storage: dict) -> dict:
    bal, hs = res["bal"], res["hs"]
    dt, ct = demand_table(inp), cooling_table(inp)
    kw, mw = peak_kw_per_household(inp), peak_mw_total(inp)
    heat_mwh, dhw_mwh = dt["난방(MWh_th)"].sum(), dt["급탕(MWh_th)"].sum()
    cool_heat_mwh = dt["냉방용 열(MWh_th)"].sum()
    gen_heat = bal["FC 발생열"].sum()

    spring_fall = bal[bal["계절"] == "봄·가을"]
    sf_sur = float(spring_fall["잉여열"].sum())
    summer = bal[bal["계절"] == "하절기"]
    s_gen, s_dem, s_sur = (float(summer["FC 발생열"].sum()), float(summer["총 열수요"].sum()), float(summer["잉여열"].sum()))
    s_months = ", ".join(f"{r['월']}({r['잉여열']:,.1f})" for _, r in summer.iterrows() if r["잉여열"] > 1e-6)
    if s_sur <= 1e-6:
        summer_res = f"하절기 FC 발생열 {s_gen:,.0f} MWh_th ≤ 총 열부하 {s_dem:,.0f} MWh_th, 하절기 잉여열 0 MWh_th"
    else:
        summer_res = (f"하절기 총량 기준 충족 (FC 발생열 {s_gen:,.0f} ≤ 총 열부하 {s_dem:,.0f} MWh_th). 다만 월별로는 냉방부하가 작은 달에 "
                      f"잉여열 합계 {s_sur:,.1f} MWh_th (발생열의 {s_sur / s_gen:.1%}) 발생: {s_months} — 축열조 또는 월별 대응 검토 필요")

    # ───────────────── 1. 분석 조건 및 산출 근거 ─────────────────
    rows = []

    def add(g, item, content, basis=""):
        rows.append({"구분": g, "항목": item, "내용": content, "산출 근거 / 비고": basis})

    g = "대상·규모"
    add(g, "총 세대수", f"{inp.households:,.0f}세대 ({inp.region})", f"Reference {inp.ref_households:g}세대 실측자료를 {inp.households / inp.ref_households:.3f}배로 환산")
    add(g, "냉방부하 기준 평형·방위", f"33평형 (냉방 적용면적 {inp.cool_area_m2:g}㎡) · 남서향 {inp.sw_ratio:.0%} / 남동향 {1 - inp.sw_ratio:.0%}",
        f"방위 보정계수 남서 {inp.sw_factor:g}, 남동 {inp.se_factor:g} (가중평균 {inp.sw_ratio * inp.sw_factor + (1 - inp.sw_ratio) * inp.se_factor:.4f})")
    add(g, "난방 환산 기준 면적", f"{inp.area_target_m2:g}㎡ (34평형 환산) ← Reference 전용 {inp.area_ref_m2:g}㎡",
        f"난방 면적 보정계수 {inp.area_target_m2:g}÷{inp.area_ref_m2:g} = {inp.area_target_m2 / inp.area_ref_m2:.4f}")
    g = "열부하 산출기준"
    add(g, "실측 근거", "130세대(전용 59㎡) 월별 난방·급탕 실측자료 [Mcal/월]",
        f"연 난방 {sum(inp.heating_130):,.0f} Mcal, 연 급탕 {sum(inp.dhw_130):,.0f} Mcal (실측 합계)")
    add(g, "난방열 환산", f"{heat_mwh:,.0f} MWh_th/년 ({heat_mwh * 3.6:,.0f} GJ)",
        f"Q난방 = Q130 × (1,000/130) × ({inp.area_target_m2:g}/{inp.area_ref_m2:g}) = Q130 × {inp.heating_factor:.4f} (면적비 보정)")
    add(g, "급탕열 환산", f"{dhw_mwh:,.0f} MWh_th/년 ({dhw_mwh * 3.6:,.0f} GJ)",
        f"Q급탕 = Q130 × (1,000/130) × ({inp.persons_target:g}/{inp.persons_ref:g}) = Q130 × {inp.dhw_factor:.4f} (거주인원비 보정, 면적비 아님). "
        f"Reference 거주인원 {inp.persons_ref:g}명은 사용자 가정")
    add(g, "단위 환산", "1 MWh = 860 Mcal = 3.6 GJ", "1 Mcal = 1.16279 kWh")
    seasons = {}
    for i, s in enumerate(inp.season_map):
        seasons.setdefault(s, []).append(f"{i + 1}")
    add(g, "계절 구분 (계산 가정)", " / ".join(f"{s}: {','.join(m)}월" for s, m in seasons.items()),
        "열 사용 우선순위 — 동절기: 급탕→난방, 하절기: 냉방→급탕→잔여난방, 봄·가을: 급탕→잔여난방")
    g = "냉방부하 산출기준"
    add(g, "세대당 최대 냉방부하", f"{kw:.3f} kW/세대 → {inp.households:,.0f}세대 {mw:.3f} MW_cool",
        f"{inp.cool_w_per_m2:g} W/㎡ × {inp.cool_area_m2:g}㎡ × ({inp.sw_ratio:g}×{inp.sw_factor:g} + {1 - inp.sw_ratio:g}×{inp.se_factor:g}) ÷ 1,000")
    heflh_txt = ", ".join(f"{m}월 {int(h)}h" for m, h in enumerate(inp.heflh, 1) if h)
    add(g, "월별 등가전부하시간", f"{heflh_txt} (합 {sum(inp.heflh):,.0f}h)", f"월 냉방량 = {mw:.3f} MW × 등가전부하시간")
    add(g, "냉방 생산량", f"{ct['냉방 생산량(MWh_cool)'].sum():,.0f} MWh_cool/년", "기존 검토 기준 2,704 MWh와 대조 (검증 탭)")
    add(g, "냉방 전력", f"일반 {ct['일반 냉방 전력(MWh_e)'].sum():,.0f} → 하이브리드 {ct['하이브리드 냉방 전력(MWh_e)'].sum():,.0f} MWh_e (절감 {cb['saving_mwh']:,.0f})",
        f"COP 일반 {inp.cop_normal:g} / 하이브리드 전기 {inp.cop_hyb_e:g}")
    add(g, "냉방용 필요 열", f"{cool_heat_mwh:,.0f} MWh_th/년", f"하이브리드 열 COP {inp.cop_hyb_h:g} (Q냉방 ÷ {inp.cop_hyb_h:g}). 연료전지 열로 무상 공급")
    add(g, "증발수량", f"{cb['water_m3']:,.0f} ㎥/년", f"{inp.water_lpm:g} L/min × 60 ÷ {inp.hyb_cool_kw:g} kW = {water_l_per_kwh_cool(inp):.2f} L/kWh_cool (냉방열 비례 가정)")
    g = "열 판매·잉여열 처리"
    add(g, "겨울철 난방열 가격", _heat_price_text(inp), "한국지역난방공사 주택용 동절기 열요금 기준 (2024.7.1 적용 요금표, 2026년 유지 안내)")
    add(g, "매열수익 인정 범위", f"{', '.join(inp.heat_sale_seasons)} 난방·급탕 공급열만 (연 {hs['매열량(MWh_th)'].sum():,.0f} MWh_th → {_eok(hs['매열수익(원)'].sum(min_count=1) if hs['매열수익(원)'].notna().any() else None)}/년)",
        "하절기 냉방용 열은 고객 무상 공급이므로 매열수익 0원")
    add(g, "봄·가을 잉여열", f"계산에 반영하지 않음 (매열수익 0원). 해당 계절 잉여열 {sf_sur:,.0f} MWh_th (연 발생열의 {sf_sur / gen_heat:.1%})",
        "열자가소비율·열폐기율·종합효율에는 잉여열이 폐기열로 반영됨")
    add(g, "하절기 잉여열", summer_res,
        f"대수 선정 기준: 하절기 FC 발생열 ≤ 하절기 총 열부하인 최대 대수 (허용 잉여 {inp.summer_surplus_tol:.0%}) → {n}대")
    g = "연료전지·에너지 단가 (추가 확인)"
    add(g, "연료전지 사양·대수", f"PureCell 400 NG {n}대: 발전 {inp.fc_elec_kw:g} kW_e · 열 {inp.fc_heat_kw:g} kW_th · 가스 {inp.fc_gas_mj_h:,.1f} MJ/h",
        f"이용률 {inp.fc_util:.0%} (연 {inp.hours_year * inp.fc_util:,.0f}h), 연 발전량 {gen_kwh_annual(inp, n) / 1e3:,.0f} MWh_e, 초기 투자비 {inp.fc_capex / 1e8:g}억원/대 (총 {inp.fc_capex * n / 1e8:,.1f}억원)")
    vat = {GAS_VAT_EXCL: f"부가세 {inp.gas_vat_rate:.0%} 가산", GAS_VAT_INCL: "부가세 포함 단가"}.get(inp.gas_vat_mode, "부가세 처리 미확인")
    add(g, "도시가스 단가", f"{inp.gas_price:,.4f} 원/MJ → 적용 {inp.gas_price_eff():,.4f} 원/MJ ({vat})",
        f"가스비 {gas_cost_hourly(inp):,.0f}원/h/대, 연 {gas_cost_annual(inp, n) / 1e8:,.2f}억원 ({n}대, 상승률 미반영 1년차)")
    p_pre = res.get("price_pre")
    add(g, "전력 매전단가", f"{inp.elec_price_220:g}원/kWh — " + ("일반 매전단가로 해석, HPS는 별도 가산(역산)" if inp.elec_mode == ELEC_S1 else "매전+HPS 포함 단가로 해석"),
        res.get("price_note", "") if p_pre is not None else "일반 매전단가 미입력 → HPS 적용 전 분석 불가")
    disc = "미입력" if inp.discount_rate is None else f"{inp.discount_rate:.1%}"
    add(g, "분석기간·할인율·목표 IRR", f"{inp.analysis_years}년 / 기준 할인율 {disc} / HPS 목표 IRR {inp.target_irr:.0%}",
        "HPS는 목표 IRR이 되도록 이분법 역산 (정액 방식·원/kWh 방식 병행)")
    add(g, "고객 요금", f"전기 {cb['elec_price']:,.1f}원/kWh · 수도 {cb['water_price']:,.0f}원/㎥",
        "고객 순편익 = 전기료 절감 − 증발수 수도비 (냉방용 열비용 미청구), 사업자 수익과 합산하지 않음")
    conditions = pd.DataFrame(rows)

    # ───────────────── 2. 최종 결론 ─────────────────
    short = float(bal["부족열"].sum())
    eta_txt = summary["종합효율 60% 충족 여부"]
    eta = annual_total_efficiency(inp, bal)
    waste = bal["잉여열"].sum() / gen_heat if gen_heat else float("nan")
    concl = [
        ("경제성 판정", summary["경제성"]),
        ("HPS 적용 전 IRR", summary["HPS 적용 전 IRR"]),
        ("HPS 적용 후 IRR", summary["HPS 적용 후 IRR"]),
        ("기준 할인율 NPV", summary["기준 할인율 NPV"]),
        ("단순 투자회수기간", summary["단순 투자회수기간"]),
        ("할인 투자회수기간", summary["할인 투자회수기간"]),
        ("필요 HPS", summary["필요 HPS"]),
        ("연간 고객편익", summary["연간 고객편익"]),
        ("종합효율 60% 충족 여부", eta_txt),
        ("적정 연료전지 대수", summary["적정 연료전지 대수"]),
        ("축열조 용량", summary["축열조 용량"]),
        ("보조열원 필요량", summary["보조열원 필요량"]),
        ("열 이용 현황", f"부족열 {short:,.0f} MWh_th — 봄·가을 잉여열은 수익 0원"),
        ("종합효율·열폐기율", f"종합효율은 연간 {eta:.1%}로 60% 기준 {'충족' if eta >= 0.60 else '미충족'}, 열폐기율 {waste:.1%}"),
        ("고객 편익의 성격", f"고객 순편익 연 {cb['net_won'] / 1e8:,.2f}억원은 별도 지표이며 사업자 IRR/NPV에 합산하지 않음"),
    ]
    conclusion = pd.DataFrame(concl, columns=["항목", "결론"])

    # ───────────────── 3. 대수별 비교 (참고) ─────────────────
    cols = ["대수", "하절기 FC 발생열(MWh_th)", "하절기 총 열부하(MWh_th)", "하절기 잉여열(MWh_th)", "하절기 조건 충족",
            "열폐기율", "종합효율", "60% 충족", "필요 HPS(억원/년)", "필요 HPS(원/kWh)"]
    units = sweep_df[cols].head(max(5, n)).copy()
    units.insert(1, "선택", ["◀ 분석 대수" if v == n else "" for v in units["대수"]])

    # ───────────────── 4. 추가 중요 내역 ─────────────────
    ex = []

    def addx(item, content):
        ex.append({"항목": item, "내용": content})

    m_pre, m_post = res.get("m_pre"), res.get("m_post")
    gen = gen_kwh_annual(inp, n)
    heat_rev = float(hs["매열수익(원)"].fillna(0).sum())
    elec_rev = gen * (p_pre if p_pre is not None else inp.elec_price_220)
    gas = gas_cost_annual(inp, n)
    addx("1년차 사업수지 구조 (미입력 비용 제외)",
         f"매전수익 {_eok(elec_rev)} + 매열수익 {_eok(heat_rev)} − 가스비 {_eok(gas)} = {_eok(elec_rev + heat_rev - gas)}/년 "
         f"(발전원가 {gas_cost_hourly(inp) / inp.fc_elec_kw:,.1f}원/kWh_e vs 매전단가 {'미입력' if p_pre is None else f'{p_pre:,.1f}원/kWh'})")
    if m_pre:
        addx("20년 누적 운영현금흐름 (투자비 제외)", f"HPS 전 {_eok(m_pre['sum_operating'])} / HPS 후 {_eok(m_post['sum_operating']) if m_post else '산정 불가'} · 초기 투자비 {_eok(inp.fc_capex * n)}")
    blocking = [m["항목"] for m in inp.missing_items() if m["경제성 계산 영향"] == "예"]
    if blocking:
        addx("투자 판단 한계", f"추가입력 필요 {len(blocking)}건이 남아 있어 본 결과는 '미반영 항목 제외' 조건부 결과이며 투자 판단 근거로 확정 불가")
    addx(f"미확정 입력 ({len(blocking)}건)", ", ".join(blocking) if blocking else "없음")
    excl = res.get("excluded") or []
    addx("계산 제외·가정 항목", " · ".join(excl) if excl else "없음")
    for i, r in enumerate(summary["핵심 리스크"], 1):
        addx(f"핵심 리스크 {i}", r)
    addx("축열조·보조열원", f"{summary['축열조 용량']} · 보조열원 필요 {short:,.0f} MWh_th/년 (연료전지 열이 부족한 동절기 난방 등은 지역난방·히트펌프 등 별도 열원 필요)")
    addx("분석 범위 한계", "월별 총량 기준 열수지 (시간별 Peak-day·축열조 SOC 시뮬레이션 미포함), 하이브리드 증발수는 냉방열 비례 가정, 성능저하 "
         + ("반영" if inp.degradation_on else "미반영"))
    extra = pd.DataFrame(ex)

    return {"conditions": conditions, "conclusion": conclusion, "units": units, "extra": extra}


def report_flat(rep: dict) -> pd.DataFrame:
    """Excel 시트용: 모든 섹션을 (섹션, 항목, 내용, 근거) 형태로 이어 붙임."""
    parts = []
    c = rep["conditions"]
    parts.append(pd.DataFrame({"섹션": "1. 분석 조건 및 산출 근거", "항목": c["구분"] + " / " + c["항목"], "내용": c["내용"], "근거/비고": c["산출 근거 / 비고"]}))
    k = rep["conclusion"]
    parts.append(pd.DataFrame({"섹션": "2. 최종 결론", "항목": k["항목"], "내용": k["결론"], "근거/비고": ""}))
    u = rep["units"]
    parts.append(pd.DataFrame({"섹션": "3. 대수별 비교", "항목": u["대수"].astype(str) + "대", "내용": u.drop(columns=["대수"]).astype(str).agg(" | ".join, axis=1), "근거/비고": ""}))
    e = rep["extra"]
    parts.append(pd.DataFrame({"섹션": "4. 추가 중요 내역", "항목": e["항목"], "내용": e["내용"], "근거/비고": ""}))
    return pd.concat(parts, ignore_index=True)
