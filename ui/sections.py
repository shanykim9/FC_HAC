"""결과 화면 섹션 A~H. 입력조건 → 월별 에너지 수지 → 연료비 → 매전·매열 → HPS → 고객 편익 → 현금흐름 → NPV·IRR → 회수 순서."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from sim import storage as stg
from sim.constants import DISCOUNT_SENSITIVITY, GJ_PER_MWH, MCAL_PER_MWH
from sim.cooling import cooling_table, peak_kw_per_household, peak_mw_total, water_l_per_kwh_cool
from sim.economics import checkpoints, display_cf
from sim.efficiency import efficiency_table
from sim.energy_balance import annual_row, demand_table
from sim.fuelcell import gas_cost_annual, gas_cost_hourly, gen_kwh_annual, monthly_business, opex_year1
from sim.inputs import ELEC_S2, Inputs, input_register
from . import charts
from .helpers import eok, formula_box, plot, show, warn_excluded

HEAT_COLS = ["난방열", "급탕열", "냉방용 열", "총 열수요", "FC 발생열", "난방 사용열", "급탕 사용열", "냉방 사용열",
             "실제 사용열(공급열)", "배관손실열", "잉여열", "부족열"]


# ───────────────────────── 계산식 문구 (UI·Excel 공용) ─────────────────────────
def formula_sets(inp: Inputs, n: int, res: dict, cb: dict) -> dict:
    kw, mw = peak_kw_per_household(inp), peak_mw_total(inp)
    gh = gas_cost_hourly(inp)
    gen = gen_kwh_annual(inp, n)
    p_pre = res.get("price_pre")
    F = {}
    F["A-2 열수요 환산·단위변환"] = [
        f"`Q난방,1000 = Q난방,130 × (1,000/130) × ({inp.area_target_m2:g}/{inp.area_ref_m2:g}) = Q난방,130 × {inp.heating_factor:.4f}`",
        f"`Q급탕,1000 = Q급탕,130 × (1,000/130) × ({inp.persons_target:g}/{inp.persons_ref:g}) = Q급탕,130 × {inp.dhw_factor:.4f}` (급탕은 면적비 보정 안 함)",
        "`MWh_th = Mcal ÷ 860` · `GJ = MWh_th × 3.6` · (1 Mcal = 1.16279 kWh)",
    ]
    F["A-3/A-4 냉방"] = [
        f"`세대당 최대 냉방부하 = {inp.cool_w_per_m2:g} W/㎡ × {inp.cool_area_m2:g} ㎡ × ({inp.sw_ratio:g}×{inp.sw_factor:g} + {1-inp.sw_ratio:g}×{inp.se_factor:g}) = {kw:.3f} kW`",
        f"`1,000세대 최대 냉방부하 = {kw:.3f} kW × {inp.households:g} = {mw:.3f} MW_cool` → `Q냉방,m = {mw:.3f} MW × HEFLH_m`",
        f"`E일반 = Q냉방 ÷ {inp.cop_normal:g}` · `E하이브리드 = Q냉방 ÷ {inp.cop_hyb_e:g}` · `Q하이브리드열 = Q냉방 ÷ {inp.cop_hyb_h:g}`",
        f"`증발수 원단위 = {inp.water_lpm:g} L/min × 60 ÷ {inp.hyb_cool_kw:g} kW = {water_l_per_kwh_cool(inp):.2f} L/kWh_cool` → `V_water(㎥) = Q냉방(MWh) × {water_l_per_kwh_cool(inp):.2f}`",
    ]
    F["B 월별 에너지수지"] = [
        f"`Q_FC,m = {inp.fc_heat_kw:g} kW × 월시간 × {inp.fc_util:.0%} × N ÷ 1,000  [MWh_th]` (N={n})",
        "`사용열 우선순위: 동절기 급탕→난방 / 하절기 냉방→급탕→잔여난방 / 봄·가을 급탕→잔여난방`",
        "`부족열 = MAX(총열수요 − Q_FC,m, 0)` · `잉여열 = MAX(Q_FC,m − 총열수요, 0)`",
        "`열자가소비율 = 실제사용열 ÷ 발생열` · `열폐기율 = 잉여열 ÷ 발생열` · `열부하충족률 = FC공급열 ÷ 총열수요`",
    ]
    F["C 연료전지 사업수지"] = [
        f"`C_gas,h = {inp.fc_gas_mj_h:,.1f} MJ/h × {inp.gas_price_eff():.4f} 원/MJ = {gh:,.0f} 원/h`",
        f"`C_gas,y = C_gas,h × 8,760h × {inp.fc_util:.0%} × N = {gas_cost_annual(inp, n)/1e8:,.3f} 억원/년` (N={n}, 상승률·할인율 미반영 1년차)",
        f"`E_FC,y = {inp.fc_elec_kw:g} kW × 8,760h × {inp.fc_util:.0%} × N = {gen:,.0f} kWh/년 = {gen/1000:,.1f} MWh_e`",
        f"`R_매전,y = E_FC,y × P_매전` (P_매전 = {'미입력' if p_pre is None else f'{p_pre:,.2f}'} 원/kWh; {res['price_note']})",
        f"`P_FC열 = P_지역난방 × {inp.fc_heat_price_ratio:.0%}` · 매열수익 = Σ(인정 계절 난방·급탕 공급열 × P_FC열) — 하절기 냉방열·잉여열은 0원",
        "`CF_y = 매전수익 + 동절기 매열수익 + HPS − 가스비 − O&M − 기타운영비`",
    ]
    pe, pw = cb["elec_price"], cb["water_price"]
    F["D 고객 편익"] = [
        f"`전기절감액 = (E일반 − E하이브리드) × {pe:,.2f} 원/kWh = {cb['saving_mwh']:,.1f} MWh × 1,000 × {pe:,.2f} = {cb['elec_saving_won']/1e8:,.3f} 억원`",
        f"`증발수비용 = {cb['water_m3']:,.0f} ㎥ × {pw:,.0f} 원/㎥ = {cb['water_cost_won']/1e8:,.3f} 억원`",
        f"`고객순편익 = 전기절감액 − 증발수비용 = {cb['net_won']/1e8:,.3f} 억원/년` (냉방용 열비용은 차감하지 않음)",
    ]
    F["E 장기 경제성"] = [
        "`CF0 = −CAPEX` · `CFt = 기본매전수익 + 동절기매열수익 + HPS − 가스비 − O&M − 기타운영비`",
        "`NPV = Σ CFt ÷ (1+r)^t` · `IRR: Σ CFt ÷ (1+IRR)^t = 0 (이분법)`",
        "`HPS 역산: IRR(CF0..CF20) = 선택한 목표 IRR 이 되는 H를 이분법으로 수치해석 (단순 '부족분+10%' 방식 아님)`",
        "`HPS(원/kWh) = 연간 HPS ÷ 연간 발전량`",
        "`단순 회수기간 = 누적 명목 CF가 처음 0 이상이 되는 시점` · `할인 회수기간 = 누적 할인 CF가 처음 0 이상이 되는 시점` · 미회수 시 '분석기간 내 미회수'",
        "`누적이익 ≠ NPV` : 누적이익은 할인하지 않은 명목 합계, NPV는 할인된 현재가치",
    ]
    F["F 종합효율"] = [
        f"`η_e = {inp.fc_elec_kw:g} kW × 3.6 MJ/kWh ÷ {inp.fc_gas_mj_h:,.1f} MJ/h = {inp.fc_elec_kw*3.6/inp.fc_gas_mj_h:.2%}`",
        "`η_h = 실제 사용열 ÷ 투입가스열` (열출력 전체가 아니라 난방·급탕·냉방에 실제 사용된 열만, 잉여·폐기열 제외)",
        "`η_total = (발전전력 + 실제 사용열) ÷ 투입가스열 ≥ 60% 이면 충족`",
    ]
    F["G 축열조"] = [
        "`Q_storage = Σ MAX(Q_load,t − Q_FC,t, 0)` · `V = Q_storage ÷ (ρ·Cp·ΔT)` (ρ=1,000 kg/㎥, Cp=4.186 kJ/kg·K, 1 MWh = 3.6×10⁶ kJ)",
        "`설계용량 = Q_storage ÷ (η충열 × η방열) ÷ (1 − 허용열손실) + 최소잔여용량` (계산 가정)",
    ]
    return F


# ───────────────────────── A ─────────────────────────
def tab_a(inp: Inputs):
    st.markdown("#### 입력조건·가정 요약")
    reg = input_register(inp)
    show(reg, dec=3)
    miss = inp.missing_items()
    st.info(f"추가입력/확인 필요 항목 {len(miss)}건 (경제성 계산 영향 {sum(m['경제성 계산 영향']=='예' for m in miss)}건) → '추가입력 필요' 탭 참조")
    return reg


# ───────────────────────── B ─────────────────────────
def tab_b(inp: Inputs, n: int, res: dict, F: dict):
    st.subheader(f"B. 월별 Energy Balance (연료전지 {n}대)")
    dt = demand_table(inp)
    st.markdown("**① 130세대 실측 → 1,000세대 환산 (Mcal·GJ·MWh_th 병기)**")
    show(dt, dec=1)
    formula_box("열수요 환산", F["A-2 열수요 환산·단위변환"])
    cool = cooling_table(inp)
    st.markdown("**② 냉방 계산 (별도 냉방부하 기준)**")
    show(cool, dec=1)
    formula_box("냉방", F["A-3/A-4 냉방"])
    unit = st.radio("③ 표시 단위", ["MWh_th", "GJ", "Mcal"], horizontal=True, key="bal_unit")
    k = {"MWh_th": 1.0, "GJ": GJ_PER_MWH, "Mcal": MCAL_PER_MWH}[unit]
    bal = res["bal"]
    v = bal[["월", "계절"] + HEAT_COLS].copy()
    v[HEAT_COLS] = v[HEAT_COLS] * k
    tot = {c: v[c].sum() for c in HEAT_COLS}
    tot.update({"월": "연간", "계절": "-"})
    v = pd.concat([v, pd.DataFrame([tot])], ignore_index=True)
    st.markdown(f"**월별 열수지 [{unit}]**")
    show(v, dec=1)
    a = annual_row(bal)
    r = bal[["월", "열자가소비율", "열폐기율", "열부하충족률"]].copy()
    r = pd.concat([r, pd.DataFrame([{"월": "연간", "열자가소비율": a["열자가소비율"], "열폐기율": a["열폐기율"], "열부하충족률": a["열부하충족률"]}])], ignore_index=True)
    show(r, pct_cols=["열자가소비율", "열폐기율", "열부하충족률"])
    formula_box("에너지수지", F["B 월별 에너지수지"])
    st.markdown("**④ 종합효율 검증 (η_total ≥ 60%)**")
    eff = efficiency_table(inp, bal)
    show(eff, dec=1, pct_cols=["전기효율", "열회수효율", "종합효율"])
    low = eff[(eff["60% 판정"] == "미충족") & (eff["구분"] != "연간")]
    st.caption(f"60% 미달 월: {', '.join(low['구분']) if len(low) else '없음'}")
    formula_box("종합효율", F["F 종합효율"])
    return eff


# ───────────────────────── C ─────────────────────────
def tab_c(inp: Inputs, n: int, res: dict, F: dict):
    st.subheader(f"C. 연료전지 사업수지 (연료전지 {n}대, 1년차 단가)")
    warn_excluded(res.get("excluded", []), res["status"])
    st.markdown("**① 가스비 (대수별 검증값)**")
    rows = [{"대수": k, "시간당 가스비(원/h)": gas_cost_hourly(inp) * k, "연간 가스비(억원)": gas_cost_annual(inp, k) / 1e8,
             "20년 단순합계(억원, 상승률·할인율 미반영)": gas_cost_annual(inp, k) / 1e8 * 20} for k in range(1, 4)]
    show(pd.DataFrame(rows), dec=2, per_col={"대수": 0, "시간당 가스비(원/h)": 0})
    st.markdown(f"**② 매전·매열·HPS** — {res['price_note']}")
    bal, hs = res["bal"], res["hs"]
    p_pre = res.get("price_pre")
    p_use = p_pre if p_pre is not None else inp.elec_price_220
    if p_pre is None:
        st.warning("일반 매전단가 미입력 → 월별표는 220원/kWh(HPS 포함 단가)로 표시합니다. HPS 전·후 구분 불가.")
    hps_annual = (res.get("hps") or {}).get("H") or 0.0
    mb = monthly_business(inp, n, bal, hs, p_use, hps_annual)
    won = [c for c in mb.columns if c.endswith("(원)")]
    mb_e = mb.copy()
    mb_e[won] = mb_e[won] / 1e8
    mb_e.columns = [c.replace("(원)", "(억원)") for c in mb_e.columns]
    tot = mb_e.sum(numeric_only=True, min_count=1)
    mb_e = pd.concat([mb_e, pd.DataFrame([{"월": "연간", **tot.to_dict()}])], ignore_index=True)
    show(mb_e, dec=3, per_col={"가스 소비량(GJ)": 0, "전력 매전량(MWh_e)": 1})
    st.caption("— 는 미입력(추가입력 필요) 항목으로 계산에서 제외됨. 스택 교체비는 연도별 현금흐름표에 반영. HPS 열은 정액 HPS 역산값(기본 시나리오).")
    st.markdown("**③ 매열수익 내역** (냉방용 무상 공급열·봄/가을 잉여열은 0원)")
    show(hs, dec=1)
    ox = opex_year1(inp, n)
    ann = [{"항목": "가스비", "금액(억원/년)": -gas_cost_annual(inp, n) / 1e8, "상태": "계산"},
           {"항목": "기본 매전수익", "금액(억원/년)": gen_kwh_annual(inp, n) * p_use / 1e8, "상태": "계산"},
           {"항목": "동절기 난방·급탕 매열수익", "금액(억원/년)": hs["매열수익(원)"].sum(min_count=1) / 1e8 if hs["매열수익(원)"].notna().any() else np.nan, "상태": "계산" if hs["매열수익(원)"].notna().all() else "일부/전부 추가입력 필요"},
           {"항목": "HPS 보상금(IRR 목표 역산, 정액)", "금액(억원/년)": hps_annual / 1e8, "상태": "역산" if res.get("hps") else "산정 불가"}]
    for k, v in ox.items():
        ann.append({"항목": k, "금액(억원/년)": np.nan if v is None else -v / 1e8, "상태": "계산" if v is not None else "추가입력 필요"})
    ann_df = pd.DataFrame(ann)
    ann_df.loc[len(ann_df)] = {"항목": "1년차 사업수지(미입력 제외 합계)", "금액(억원/년)": ann_df["금액(억원/년)"].sum(), "상태": "조건부" if res.get("excluded") else "계산"}
    st.markdown("**④ 연간 사업수지 (1년차, 사업자 기준 — 고객 편익 미포함)**")
    show(ann_df, dec=3)
    formula_box("사업수지", F["C 연료전지 사업수지"])
    return mb_e, hs, ann_df


# ───────────────────────── D ─────────────────────────
def tab_d(inp: Inputs, cb_table, cb, cb_month, F):
    st.subheader("D. 고객 편익 (사업자 수익과 합산하지 않음)")
    show(cb_table, dec=2)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("전력 절감량", f"{cb['saving_mwh']:,.1f} MWh/년")
    k2.metric("전기료 절감액", f"{cb['elec_saving_won']/1e8:,.3f} 억원/년")
    k3.metric("증발수 / 수도비", f"{cb['water_m3']:,.0f} ㎥ / {cb['water_cost_won']/1e8:,.3f} 억원")
    k4.metric("고객 순편익", f"{cb['net_won']/1e8:,.3f} 억원/년", f"세대당 {cb['net_per_hh_won']/1e4:,.2f} 만원/년")
    st.caption(f"전기단가: {cb['elec_price']:,.2f} 원/kWh ({cb['elec_note']}) · 수도단가: {cb['water_price']:,.0f} 원/㎥ ({cb['water_note']})")
    if "scenario_partload" in cb:
        s = cb["scenario_partload"]
        st.info(f"[별도 시나리오: 부분부하 증발수 비비례] 증발수 {s['water_m3']:,.0f} ㎥, 수도비 {s['water_cost_won']/1e8:,.3f} 억원, 순편익 {s['net_won']/1e8:,.3f} 억원/년")
    else:
        st.caption("부분부하 증발수 비비례 시나리오: 자료 미입력으로 계산하지 않음(추가입력 필요).")
    st.markdown("**월별**")
    show(cb_month, dec=3, per_col={"일반 전력(MWh_e)": 1, "하이브리드 전력(MWh_e)": 1, "증발수(㎥)": 0})
    formula_box("고객 편익", F["D 고객 편익"])


# ───────────────────────── E ─────────────────────────
def tab_e(inp: Inputs, n: int, res: dict, F: dict):
    st.subheader(f"E. 장기 경제성 (연료전지 {n}대, {inp.analysis_years}년)")
    warn_excluded(res.get("excluded", []), res["status"])
    if res["status"] == "hold":
        return
    st.caption(f"전력 매전 해석: {res['price_note']}")
    if res.get("cf_pre") is None:
        st.error("일반 매전단가(HPS 제외)가 미입력이라 HPS 적용 전 IRR·필요 HPS를 산정할 수 없습니다.")
    else:
        hps, mp, mq = res["hps"], res["m_pre"], res.get("m_post")
        st.markdown("**① HPS 보상 역산 (목표 IRR %.0f%%)**" % (inp.target_irr * 100))
        ref = inp.discount_rate
        if hps.get("H") is not None:
            k1, k2, k3 = st.columns(3)
            k1.metric(f"필요 HPS (목표 IRR {inp.target_irr:.0%})", f"{hps['h']:,.1f} 원/kWh")
            k2.metric("연간 필요 HPS 보상금(정액)", f"{hps['H']/1e8:,.2f} 억원/년")
            k3.metric("HPS 적용 후 IRR", "산정 불가" if hps.get("irr_after") is None else f"{hps['irr_after']:.2%}")
            if not hps.get("needed", True):
                st.caption("HPS 적용 전에도 IRR이 목표 IRR 이상이라 HPS는 0으로 표시됩니다.")
        rows = [
            ["연간 필요 HPS 보상금 (정액, 억원/년)", eok(hps.get("H")), eok(hps.get("H_kwh_equiv_y1"))],
            ["필요 HPS 단가 (원/kWh)", hps.get("h_const_equiv"), hps.get("h")],
            ["HPS 적용 전 IRR", mp["irr"], mp["irr"]],
            ["HPS 적용 후 IRR", hps.get("irr_after"), hps.get("irr_after_kwh")],
            [f"HPS 적용 전 NPV (억원, {'기준 할인율 ' + format(ref, '.1%') if ref is not None else '기준 할인율 미입력'})", eok(mp["npv"]), eok(mp["npv"])],
            ["HPS 적용 후 NPV (억원)", eok(mq["npv"]) if mq else None, eok(mq["npv"]) if mq else None],
        ]
        d = pd.DataFrame(rows, columns=["항목", "기본: 매년 동일 정액 HPS", "발전량 비례 원/kWh 방식"])
        for c in d.columns[1:]:
            d[c] = pd.to_numeric(d[c], errors="coerce")
        pc = d["항목"].str.contains("IRR")
        d.loc[pc, d.columns[1:]] = d.loc[pc, d.columns[1:]] * 100
        d["항목"] = d["항목"].where(~pc, d["항목"] + " (%)")
        show(d, dec=3)
        if hps.get("note"):
            st.info(hps["note"])
        if not inp.degradation_on:
            st.caption("성능저하 반영을 체크하지 않아 두 방식의 현금흐름이 동일합니다(발전량이 매년 같음).")
        if "m_bundled" in res:
            mb = res["m_bundled"]
            st.markdown(f"**220원/kWh(매전+HPS 포함) 적용 시:** IRR {'산정 불가' if mb['irr'] is None else format(mb['irr'], '.2%')}"
                        f" · 내재 HPS = (220 − {inp.elec_price_base:,.1f}) × 발전량 = {(inp.elec_price_220 - inp.elec_price_base) * res['gen_kwh'] / 1e8:,.2f} 억원/년 vs 필요 HPS {('산정 불가' if hps.get('H') is None else format(eok(hps['H']), ',.2f'))} 억원/년")
        st.markdown("**② 연도별 현금흐름 (억원, 0~%d년)** — HPS 적용 전" % inp.analysis_years)
        show(display_cf(res["cf_pre"]), dec=3, per_col={"연도": 0})
        if res.get("cf_post") is not None:
            with st.expander("HPS 적용 후 현금흐름 (IRR 목표 달성)"):
                show(display_cf(res["cf_post"]), dec=3, per_col={"연도": 0})
        st.markdown("**③ NPV·IRR·회수기간**")
        pb = pd.DataFrame([
            ["IRR", mp["irr"], hps.get("irr_after")],
            ["NPV (억원)", eok(mp["npv"]), eok(mq["npv"]) if mq else None],
            ["단순 회수기간", mp["payback_text"], mq["payback_text"] if mq else "산정 불가"],
            ["할인 회수기간", mp["dpayback_text"], mq["dpayback_text"] if mq else "산정 불가"],
            ["누적 운영현금흐름 합(투자비 제외, 억원)", mp["sum_operating"] / 1e8, mq["sum_operating"] / 1e8 if mq else None],
        ], columns=["지표", "HPS 적용 전", "HPS 적용 후"])
        for i in (0,):
            for c in ("HPS 적용 전", "HPS 적용 후"):
                v = pb.loc[i, c]
                pb.loc[i, c] = "산정 불가(IRR 해 없음)" if v is None else f"{v:.2%}"
        for i in (1, 4):
            for c in ("HPS 적용 전", "HPS 적용 후"):
                v = pb.loc[i, c]
                pb.loc[i, c] = "기준 할인율 미입력" if (v is None and i == 1) else ("—" if v is None else f"{v:,.3f}")
        show(pb)
        st.markdown("**④ 12년·15년·20년 시점 누적값** (누적이익 ≠ NPV)")
        c1, c2 = st.columns(2)
        with c1:
            st.caption("HPS 적용 전")
            show(checkpoints(inp, res["cf_pre"]), dec=3)
        with c2:
            if res.get("cf_post") is not None:
                st.caption("HPS 적용 후")
                show(checkpoints(inp, res["cf_post"]), dec=3)
        st.markdown("**⑤ 할인율별 NPV 민감도** — 3/5/7/10%는 비교구간일 뿐 기준 할인율을 확정한 것이 아님")
        show(res["sens"], dec=2, pct_cols=["할인율"])
    formula_box("장기 경제성", F["E 장기 경제성"])


# ───────────────────────── F ─────────────────────────
def tab_f(summary: dict, n_heat):
    st.subheader("F. 최종 결론 (경영진 요약)")
    for k in ["경제성", "HPS 적용 전 IRR", "HPS 적용 후 IRR", "기준 할인율 NPV", "단순 투자회수기간", "할인 투자회수기간", "필요 HPS",
              "연간 고객편익", "종합효율 60% 충족 여부", "적정 연료전지 대수", "축열조 용량", "보조열원 필요량"]:
        st.markdown(f"- **{k}:** {summary[k]}")
    if n_heat:
        st.caption(f"참고: 종합효율 60%를 유지하는 최대 대수는 {n_heat}대입니다. 대수 선정은 하절기 열 잉여 방지 기준이며, NPV·IRR 결과는 별도로 확인하세요.")
    st.markdown("**핵심 리스크**")
    for i, r in enumerate(summary["핵심 리스크"], 1):
        st.markdown(f"{i}. {r}")
    st.markdown("**최종 판단**")
    for ln in summary["최종 판단"]:
        st.markdown(f"- {ln}")


# ───────────────────────── G ─────────────────────────
def tab_g(inp: Inputs, n: int, F: dict) -> dict:
    st.subheader("G. 축열조 및 피크 대응")
    st.info("월별 총량만으로 축열조 용량을 확정하지 않습니다. Peak-day 시간별 자료를 입력해야 계산되며, 미입력 시 '축열조 용량 산정 불가, 추가입력 필요'로 표시됩니다.")
    use_rated = st.checkbox(f"FC 시간별 공급열 = 정격 열출력 × {n}대 (연속 정격운전 가정, 이용률 미반영)", key="stg_rated")
    base = stg.empty_hourly()
    if use_rated:
        base["FC 공급열(MWh_th/h)"] = inp.fc_heat_kw * n / 1000
    try:
        ed = st.data_editor(base, key="stg_ed", hide_index=True, width="stretch", num_rows="fixed", disabled=["시각"])
    except TypeError:
        ed = st.data_editor(base, key="stg_ed", hide_index=True, use_container_width=True, num_rows="fixed", disabled=["시각"])
    c = st.columns(4)
    from .inputs_form import opt
    with c[0]:
        ts = opt("축열조 공급 가능 온도", "stg_ts", unit="℃", step=1.0)
        tr = opt("축열조 환수온도", "stg_tr", unit="℃", step=1.0)
    with c[1]:
        loss = opt("허용 열손실", "stg_loss", pct=True, unit="%", step=0.5)
        mn = opt("최소 잔여용량", "stg_min", unit="MWh_th", step=0.1)
    with c[2]:
        ec = opt("충열효율", "stg_ec", pct=True, unit="%", step=1.0)
        ed_ = opt("방열효율", "stg_ed_eff", pct=True, unit="%", step=1.0)
    with c[3]:
        th = opt("목표 피크 대응시간", "stg_th", unit="h", step=1.0)
    si = stg.StorageInputs(hourly=ed, supply_temp=ts, return_temp=tr, loss_ratio=loss, min_residual=mn,
                           eta_charge=ec, eta_discharge=ed_, target_hours=th, cop_heat=inp.cop_hyb_h)
    out = stg.compute(si)
    if not out["ok"]:
        st.warning(f"**{out['message']}** — 부족 항목: " + ", ".join(out["missing"]))
    else:
        k = st.columns(4)
        k[0].metric("연료전지 직접 공급열", f"{out['direct']:,.2f} MWh_th/일")
        k[1].metric("축열조 충전열", f"{out['charge']:,.2f} MWh_th/일")
        k[2].metric("축열조 방열량", f"{out['discharge']:,.2f} MWh_th/일")
        k[3].metric("축열조로 처리하지 못한 부족열", f"{out['unmet']:,.2f} MWh_th/일")
        st.markdown(f"- 필요 축열용량 Q_storage = **{out['q_storage']:,.2f} MWh_th** · 목표 대응시간 최대 연속 부족열 {out['q_peakT']:,.2f} MWh_th(참고)\n"
                    f"- 설계 용량 = **{out['q_design']:,.2f} MWh_th** → 물 용량 V = **{out['volume_m3']:,.0f} ㎥** (ΔT {out['dT']:.1f}℃, 순수 필요 {out['volume_effective_m3']:,.0f} ㎥)\n"
                    f"- 지역난방 또는 히트펌프 보조열량(일): **{out['unmet']:,.2f} MWh_th**")
        show(out["hourly"], dec=3)
        st.caption("충·방열 총량은 24시간 합계 기준이며 시간 순서별 SOC 시뮬레이션은 포함하지 않습니다(계산 가정).")
    formula_box("축열조", F["G 축열조"])
    out["_inputs_df"] = ed
    return out


# ───────────────────────── H ─────────────────────────
def tab_h(inp: Inputs, n: int, res: dict, sweep_df: pd.DataFrame):
    st.subheader("H. 그래프")
    bal = res["bal"]
    c1, c2 = st.columns(2)
    with c1:
        plot(charts.demand_by_use(bal), "g1")
        plot(charts.used_surplus_short(bal), "g3")
    with c2:
        plot(charts.demand_vs_gen(bal), "g2")
        plot(charts.cooling_power(cooling_table(inp)), "g4")
    if res.get("cf_pre") is None:
        st.warning("경제성 그래프는 계산 보류/산정 불가 상태라 표시하지 않습니다 (추가입력 필요).")
    else:
        c1, c2 = st.columns(2)
        with c1:
            plot(charts.annual_cf(res["cf_pre"], res.get("cf_post")), "g5")
            net = res["cf_pre"]["순현금흐름"].to_numpy()
            rates = [inp.discount_rate] if inp.discount_rate is not None else DISCOUNT_SENSITIVITY
            plot(charts.cum_discounted(res["cf_pre"], rates, net), "g7")
            plot(charts.npv_sensitivity(res["sens"]), "g9")
        with c2:
            plot(charts.cum_nominal(res["cf_pre"]), "g6")
            plot(charts.hps_before_after(res["cf_pre"], res.get("cf_post")), "g8")
            plot(charts.by_units(sweep_df), "g10")
    if res.get("cf_pre") is None:
        plot(charts.by_units(sweep_df), "g10")


# ───────────────────────── 대수 비교 ─────────────────────────
def tab_units(sweep_df, n_rec, why, n_eff, n):
    st.subheader("연료전지 대수별 비교")
    show(sweep_df, dec=2, pct_cols=["열자가소비율", "열폐기율", "열부하충족률", "종합효율", "IRR(HPS 전)"], per_col={"대수": 0})
    st.markdown(f"- **대수 선정 기준(하절기 열 잉여 방지):** {n_rec}대 — {why}\n- **참고:** 종합효율 60% 유지 최대 {n_eff if n_eff else '없음'}대 · NPV·IRR은 비교용으로만 표시\n- **현재 분석 대수:** {n}대 (자동 추천 또는 수동 지정)")
    st.caption("하절기에 열이 남지 않도록 FC 발생열 ≤ 하절기 총 열부하인 최대 대수를 고릅니다. 약간의 잉여는 '하절기 허용 잉여열[%]'(축열조 저장분)로 완화할 수 있습니다.")


# ───────────────────────── 최종검토 리포트 ─────────────────────────
def tab_report(rep: dict, n: int):
    st.subheader("최종검토 리포트")
    st.caption(f"연료전지 {n}대 기준 · 모든 수치는 현재 입력값과 계산 결과에서 자동 생성됩니다 (입력을 바꾸면 리포트도 바뀜).")
    st.markdown("### 1. 분석 조건 및 산출 근거")
    show(rep["conditions"])
    st.markdown("### 2. 최종 결론")
    show(rep["conclusion"])
    st.markdown("### 3. 연료전지 대수별 비교 (참고)")
    show(rep["units"], dec=1, pct_cols=["열폐기율", "종합효율"], per_col={"대수": 0, "필요 HPS(억원/년)": 2})
    st.caption("대수 선정은 하절기 열 잉여 방지 기준이며, 필요 HPS는 목표 IRR 역산값(비교용)입니다.")
    st.markdown("### 4. 추가 중요 내역 (수익 구조·미확정 입력·리스크·한계)")
    show(rep["extra"])


# ───────────────────────── 추가입력 ─────────────────────────
def tab_missing(inp: Inputs):
    st.subheader("J. 추가입력 필요 항목")
    st.caption("다음 값은 임의로 생성하지 않았습니다. 입력 전까지 경제성 계산을 보류하거나 민감도/조건부 결과로만 제공합니다.")
    m = pd.DataFrame(inp.missing_items())
    show(m)
    return m
