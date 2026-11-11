"""입력 UI. 모든 입력값을 화면에서 수정할 수 있으며, 미입력(추가입력 필요)은 빈 칸으로 둔다."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from sim.constants import DEFAULT_DISCOUNT_RATE, DEFAULT_TARGET_IRR, DISCOUNT_RATE_OPTIONS, TARGET_IRR_OPTIONS, DEFAULT_DISTRICT_HEAT_PRICE_MCAL, HEAT_PRICE_UNITS, MONTH_LABELS, SEASONS
from sim.inputs import (ELEC_COMPONENT_KEYS, ELEC_S1, ELEC_S2, GAS_VAT_EXCL, GAS_VAT_INCL, GAS_VAT_UNKNOWN,
                        N_AUTO, N_MANUAL, OEM_PER_KWH, OEM_PER_UNIT, WATER_COMPONENT_KEYS, Inputs)


def opt(label, key, pct=False, value=None, vmin=0.0, step=None, fmt=None, help=None, unit=""):
    """추가입력 필요(기본 빈 칸=None) 숫자 입력. pct=True면 %로 입력받아 비율로 반환."""
    lab = f"{label} [{unit}]" if unit else label
    v = st.number_input(lab, value=value, min_value=float(vmin), step=step, format=fmt, key=key, help=help,
                        placeholder="추가입력 필요")
    if v is None:
        return None
    return v / 100.0 if pct else float(v)


def _editor(df, key, **kw):
    try:
        return st.data_editor(df, key=key, hide_index=True, width="stretch", num_rows="fixed", **kw)
    except TypeError:
        return st.data_editor(df, key=key, hide_index=True, use_container_width=True, num_rows="fixed", **kw)


def build_inputs() -> Inputs:
    inp = Inputs()

    # ── 분석 설정 ──
    st.markdown("#### 분석 설정")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        mode = st.radio("미입력(추가입력 필요) 항목 처리", ["참고용 제외계산", "엄격 보류"], key="strict",
                        help="참고용: 미입력 항목을 계산에서 제외하고 경고를 표시(0원 확정 아님). 엄격 보류: 미입력이 있으면 경제성(NPV/IRR) 계산 자체를 보류.")
        inp.strict_hold = mode == "엄격 보류"
    with c2:
        inp.n_mode = st.radio("분석 연료전지 대수", [N_AUTO, N_MANUAL], key="n_mode")
        inp.summer_surplus_tol = st.number_input("하절기 허용 잉여열 [%] (축열조 저장 허용분)", value=0.0, min_value=0.0, step=1.0, key="stol") / 100
        inp.n_manual = int(st.number_input("수동 지정 대수", value=2, min_value=1, max_value=50, step=1, key="n_manual"))
    with c3:
        inp.n_max = int(st.number_input("대수 비교 범위(1~N대)", value=10, min_value=2, max_value=30, step=1, key="n_max"))
        t_opts = [round(x * 100) for x in TARGET_IRR_OPTIONS]
        t_sel = st.selectbox("HPS 역산 목표 IRR [%]", t_opts, index=t_opts.index(round(DEFAULT_TARGET_IRR * 100)),
                             key="tirr", format_func=lambda v: f"{v:d}%",
                             help="5%~15% (1% 단위). 이 IRR이 되도록 필요 HPS를 역산합니다. 기본 10%.")
        inp.target_irr = t_sel / 100
    with c4:
        d_opts = [round(x * 100, 1) for x in DISCOUNT_RATE_OPTIONS]
        d_sel = st.selectbox("기준 할인율 [%] (NPV·할인회수기간 산정용)", d_opts, index=d_opts.index(round(DEFAULT_DISCOUNT_RATE * 100, 1)),
                             key="disc", format_func=lambda v: f"{v:.1f}%",
                             help="4.0%~10.0% (0.5% 단위). NPV와 할인 회수기간 계산에 사용합니다. 기본 7%.")
        inp.discount_rate = d_sel / 100

    # ── A-1 ──
    with st.expander("A-1. 공동주택 조건", expanded=False):
        a, b, c = st.columns(3)
        inp.households = a.number_input("세대수 [세대]", value=1000, min_value=1, step=10, key="hh")
        inp.ref_households = b.number_input("Reference 세대수 [세대]", value=130, min_value=1, step=1, key="rhh")
        inp.analysis_years = int(c.number_input("분석기간 [년]", value=20, min_value=1, max_value=40, step=1, key="yrs"))
        inp.area_target_m2 = a.number_input("분석 대상 환산면적(34평형) [㎡]", value=112.4, min_value=1.0, step=0.1, key="atg")
        inp.area_ref_m2 = b.number_input("Reference 전용면적 [㎡]", value=59.0, min_value=1.0, step=0.1, key="aref")
        inp.region = c.text_input("기준 지역", value="수도권", key="region")
        inp.persons_target = a.number_input("분석 대상 거주인원 [인/세대]", value=4.0, min_value=0.5, step=0.5, key="ptg")
        inp.persons_ref = b.number_input("Reference 거주인원 [인/세대] (사용자 가정 4명)", value=4.0, min_value=0.5, step=0.1, key="pref")
        inp.persons_ref_confirmed = c.checkbox("Reference 거주인원 확인 완료", value=True, key="pref_ok")
        st.caption(f"난방 면적 보정계수 = {inp.area_target_m2:g}÷{inp.area_ref_m2:g} = **{inp.area_target_m2/inp.area_ref_m2:.3f}** · "
                   f"급탕 인원 보정계수(면적비 아님) = {inp.persons_target:g}÷{inp.persons_ref:g} = **{inp.persons_target/inp.persons_ref:.3f}**")

    # ── A-2 ──
    with st.expander("A-2. 130세대(전용 59㎡) 난방·급탕 실측자료 [Mcal/월] · 계절 구분", expanded=False):
        base = pd.DataFrame({"월": MONTH_LABELS, "난방 실측(Mcal/월)": inp.heating_130, "급탕 실측(Mcal/월)": inp.dhw_130, "계절(계산 가정)": inp.season_map})
        ed = _editor(base, "ed_meas", disabled=["월"], column_config={
            "난방 실측(Mcal/월)": st.column_config.NumberColumn(format="%.3f", min_value=0.0),
            "급탕 실측(Mcal/월)": st.column_config.NumberColumn(format="%.3f", min_value=0.0),
            "계절(계산 가정)": st.column_config.SelectboxColumn(options=SEASONS, required=True)})
        inp.heating_130 = ed["난방 실측(Mcal/월)"].fillna(0).tolist()
        inp.dhw_130 = ed["급탕 실측(Mcal/월)"].fillna(0).tolist()
        inp.season_map = ed["계절(계산 가정)"].tolist()
        st.caption("계절 구분 기본값: 봄 3~5월, 여름(하절기) 6~8월, 가을 9~11월, 겨울(동절기) 12~2월. 봄·가을은 동일 규칙이며 수정 가능합니다.")

    # ── A-3 / A-4 ──
    with st.expander("A-3. 냉방부하 · A-4. 하이브리드 콘덴싱에어컨", expanded=False):
        a, b, c, d = st.columns(4)
        inp.cool_w_per_m2 = a.number_input("세대당 기준 냉방부하 [W/㎡]", value=59.2, min_value=0.1, step=0.1, key="cw")
        inp.cool_area_m2 = b.number_input("냉방 적용면적 [㎡]", value=84.8, min_value=0.1, step=0.1, key="ca")
        inp.sw_ratio = c.number_input("남서향 비율 [%]", value=60.0, min_value=0.0, max_value=100.0, step=1.0, key="swr") / 100
        d.metric("남동향 비율", f"{(1-inp.sw_ratio)*100:.0f}%")
        inp.sw_factor = a.number_input("남서향 보정계수", value=1.08, min_value=0.1, step=0.01, key="swf")
        inp.se_factor = b.number_input("남동향 보정계수", value=1.02, min_value=0.1, step=0.01, key="sef")
        inp.cop_normal = c.number_input("일반 시스템에어컨 COP", value=3.5, min_value=0.1, step=0.1, key="cn")
        inp.cop_hyb_e = d.number_input("하이브리드 전기 COP", value=5.2, min_value=0.1, step=0.1, key="ce")
        inp.cop_hyb_h = a.number_input("하이브리드 열 COP", value=1.7, min_value=0.1, step=0.1, key="ch")
        inp.hyb_cool_kw = b.number_input("정격 냉방능력 [kW]", value=11.0, min_value=0.1, step=0.5, key="hck")
        inp.hyb_elec_kw = c.number_input("정격 소비전력 [kW]", value=2.1, min_value=0.1, step=0.1, key="hek")
        inp.hyb_heat_kw = d.number_input("정격 열 소비량 [kW_th]", value=6.0, min_value=0.1, step=0.1, key="hhk")
        inp.water_lpm = a.number_input("증발수 사용량 [L/min]", value=1.1, min_value=0.0, step=0.1, key="wl")
        with b:
            inp.water_partload_factor = opt("부분부하 증발수 보정(비례 대비 배수)", "wpl", unit="배", step=0.05,
                                            help="비례 제어가 아닐 때의 자료가 있을 때만 입력(별도 시나리오). 미입력이면 가정하지 않음.")
        heflh = pd.DataFrame({"월": MONTH_LABELS, "등가전부하시간(h)": inp.heflh})
        e2 = _editor(heflh, "ed_heflh", disabled=["월"], column_config={"등가전부하시간(h)": st.column_config.NumberColumn(min_value=0.0, format="%.1f")})
        inp.heflh = e2["등가전부하시간(h)"].fillna(0).tolist()

    # ── A-5 / A-6 ──
    with st.expander("A-5. 연료전지(PureCell 400 NG, 1대 기준) · A-6. 도시가스", expanded=False):
        a, b, c, d = st.columns(4)
        inp.fc_elec_kw = a.number_input("발전출력 [kW_e]", value=400.0, min_value=1.0, step=10.0, key="fe")
        inp.fc_heat_kw = b.number_input("열출력 [kW_th]", value=446.0, min_value=1.0, step=10.0, key="fh")
        inp.fc_gas_mj_h = c.number_input("가스 소비열량 [MJ/h]", value=3798.2, min_value=1.0, step=10.0, key="fg")
        inp.fc_util = d.number_input("연간 이용률 [%]", value=95.0, min_value=1.0, max_value=100.0, step=0.5, key="fu") / 100
        inp.fc_capex = a.number_input("초기 투자비 [억원/대]", value=25.0, min_value=0.1, step=0.5, key="fcx") * 1e8
        inp.gas_price = b.number_input("도시가스 요금 [원/MJ]", value=25.0573, min_value=0.0, step=0.1, format="%.4f", key="gp")
        inp.gas_vat_mode = c.selectbox("가스단가 부가세 처리 (확인 필요)", [GAS_VAT_UNKNOWN, GAS_VAT_INCL, GAS_VAT_EXCL], index=2, key="gvat")
        inp.gas_vat_rate = d.number_input("부가가치세율 [%]", value=10.0, min_value=0.0, step=1.0, key="gvr") / 100
        with a:
            inp.gas_escalation = opt("가스가격 상승률", "gesc", pct=True, unit="%/년", vmin=-100.0, step=0.5)
        st.caption(f"연간 등가 운전시간 = 8,760h × {inp.fc_util:.0%} = **{inp.hours_year*inp.fc_util:,.0f} h** · PF 미적용 · 연간 가스 투입 = {inp.fc_gas_mj_h*inp.hours_year*inp.fc_util:,.0f} MJ/대")

    # ── A-7 / A-8 ──
    with st.expander("A-7. 전력 매전 · A-8. 열 판매", expanded=False):
        inp.elec_mode = st.radio("220원/kWh의 성격 (HPS 중복계상 방지를 위해 반드시 구분)", [ELEC_S1, ELEC_S2], key="emode")
        inp.elec_mode_confirmed = st.checkbox("위 해석을 확인했습니다 (미확인 시 '추가입력 필요'로 표시)", value=True, key="emode_ok")
        a, b, c = st.columns(3)
        inp.elec_price_220 = a.number_input("기존 예비 검토단가 [원/kWh]", value=220.0, min_value=0.0, step=1.0, key="e220")
        with b:
            inp.elec_price_base = opt("일반 매전단가 (HPS 제외)", "ebase", unit="원/kWh", step=1.0, help="'HPS 포함' 선택 시 필요")
        with c:
            inp.elec_escalation = opt("전력가격 상승률", "eesc", pct=True, unit="%/년", vmin=-100.0, step=0.5)
        st.markdown("---")
        a, b, c, d = st.columns(4)
        inp.heat_price_unit = a.selectbox("지역난방 열요금 단위", list(HEAT_PRICE_UNITS), key="hpu")
        inp.fc_heat_price_ratio = b.number_input("FC 매열단가 비율 [%]", value=70.0, min_value=0.0, max_value=100.0, step=1.0, key="hpr") / 100
        inp.heat_sale_seasons = c.multiselect("매열수익 인정 계절", SEASONS, default=["동절기"], key="hss",
                                              help="기본: 동절기 난방·급탕만. 하절기 냉방용 열(무상)·잉여열은 계절과 무관하게 항상 0원.")
        with d:
            inp.heat_escalation = opt("열가격 상승률", "hesc", pct=True, unit="%/년", vmin=-100.0, step=0.5)
        with a:
            inp.pipe_loss = opt("열배관 손실률", "ploss", pct=True, unit="%", step=0.5)
        # 기본값: 한국지역난방공사 동절기 열요금(115.59원/Mcal)을 선택한 단위로 환산해 동절기 월에 채움
        conv = HEAT_PRICE_UNITS[inp.heat_price_unit]
        hp_default = [None if p is None else round(p * HEAT_PRICE_UNITS["원/Mcal"] / conv, 6)
                      for p in DEFAULT_DISTRICT_HEAT_PRICE_MCAL]
        hp = pd.DataFrame({"월": MONTH_LABELS, f"지역난방 열요금({inp.heat_price_unit})": hp_default})
        e3 = _editor(hp, "ed_heatprice_" + inp.heat_price_unit, disabled=["월"], column_config={
            f"지역난방 열요금({inp.heat_price_unit})": st.column_config.NumberColumn(min_value=0.0, format="%.4f")})
        inp.district_heat_price = [None if pd.isna(v) else float(v) for v in e3.iloc[:, 1]]
        st.caption("기본값: 한국지역난방공사 주택용 동절기 열요금 115.59 원/Mcal (= 99.41 원/kWh, 2024.7.1 적용 요금표·2026년 유지 안내). "
                   "동절기(12·1·2월)에만 입력되어 있으며, 빈 칸은 '추가입력 필요'로 매열수익에서 제외됩니다. 단위를 바꾸면 값이 자동 환산됩니다.")

    # ── A-9 ──
    with st.expander("A-9. 고객 전기요금·수도요금", expanded=False):
        a, b = st.columns(2)
        with a:
            st.markdown("**전기요금 (주택용 고압 2단계 한계단가)**")
            inp.use_elec_components = st.checkbox("항목별로 입력(합계 사용)", key="uec")
            inp.elec_eff_price = st.number_input("실효 전기단가 [원/kWh]", value=211.9, min_value=0.0, step=0.1, key="eff")
            if inp.use_elec_components:
                for k in ELEC_COMPONENT_KEYS:
                    inp.elec_components[k] = opt(k, f"ec_{k}", unit="원/kWh", step=0.1, fmt="%.3f")
        with b:
            st.markdown("**수도요금**")
            inp.use_water_components = st.checkbox("항목별로 입력(합계 사용)", key="uwc")
            inp.water_price = st.number_input("수도 총단가 [원/㎥]", value=1230.0, min_value=0.0, step=10.0, key="wp")
            if inp.use_water_components:
                for k in WATER_COMPONENT_KEYS:
                    inp.water_components[k] = opt(k, f"wc_{k}", unit="원/㎥", step=1.0)

    # ── 비용·경제성 변수 ──
    with st.expander("E. 비용·경제성 변수 (전부 '추가입력 필요' — 빈 칸 = 미입력, 0 입력 = 0원 확정)", expanded=False):
        a, b, c = st.columns(3)
        with a:
            inp.oem_unit = st.selectbox("O&M·LTSA 단위", [OEM_PER_UNIT, OEM_PER_KWH], key="oemu")
            inp.oem_value = opt("O&M·LTSA", "oem", unit=inp.oem_unit, step=1000.0)
            inp.stack_interval = opt("스택 교체주기", "sint", unit="년", step=1.0)
            inp.stack_cost = opt("스택 교체비", "scost", unit="원/대", step=1e7, fmt="%.0f")
        with b:
            inp.aux_kw = opt("연료전지 보조동력", "auxkw", unit="kW/대", step=1.0)
            inp.aux_price = opt("보조동력 적용 전력단가", "auxp", unit="원/kWh", step=1.0)
            inp.insurance = opt("보험료·제세공과금", "ins", unit="원/년/대", step=1e6, fmt="%.0f")
            inp.other_opex = opt("기타 운영비", "oth", unit="원/년(전체)", step=1e6, fmt="%.0f")
        with c:
            inp.inflation = opt("물가상승률(운영비·교체비·철거비)", "infl", pct=True, unit="%/년", vmin=-100.0, step=0.5)
            inp.subsidy = opt("정부보조금(0년차)", "sub", unit="원", step=1e8, fmt="%.0f")
            inp.tax_credit = opt("세액공제 총액", "tax", unit="원", step=1e8, fmt="%.0f")
            inp.tax_credit_year = int(st.number_input("세액공제 반영 연차", value=1, min_value=0, max_value=40, step=1, key="tcy"))
        a, b, c = st.columns(3)
        with a:
            inp.salvage = opt("잔존가치(최종연도)", "salv", unit="원/대", step=1e8, fmt="%.0f")
        with b:
            inp.decom = opt("철거비(최종연도)", "decom", unit="원/대", step=1e7, fmt="%.0f")
        with c:
            inp.degradation_on = st.checkbox("성능저하(발전량 감소) 반영", key="deg_on",
                                             help="체크 시에만 반영. 반영하면 '정액 HPS'와 '원/kWh HPS'가 달라집니다.")
            if inp.degradation_on:
                inp.degradation = opt("연간 발전량 감소율", "deg", pct=True, unit="%/년", step=0.1)
        st.markdown("**보조열원(결론 표시용, 사업자 현금흐름 미포함)**")
        a, b, c = st.columns(3)
        inp.aux_heat_type = a.text_input("보조열원 종류", value="", key="aht", placeholder="예: 지역난방 / 히트펌프")
        with b:
            inp.aux_heat_eff = opt("보조열원 효율(COP 또는 효율)", "ahe", unit="-", step=0.05)
        with c:
            inp.aux_heat_price = opt("보조열원 에너지단가", "ahp", unit="원/kWh", step=1.0)

    # ── 입력 검증 ──
    if inp.fc_heat_kw <= 0 or inp.households <= 0:
        st.error("입력값 오류")
        st.stop()
    return inp
