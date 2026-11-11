"""연료전지 + 하이브리드 콘덴싱에어컨 사업성 시뮬레이터 (Streamlit).

실행: streamlit run app.py
"""
import streamlit as st

from sim.cooling import cooling_table
from sim.customer import customer_benefit
from sim.economics import display_cf, run_economics
from sim.excel_export import build_excel
from sim.inputs import N_AUTO, input_register
from sim.scenarios import recommend, sweep
from sim.summary import executive_summary
from sim.validation import validate
from sim.energy_balance import demand_table
from sim.efficiency import efficiency_table
from sim.fuelcell import monthly_business
from sim.report import build_report, report_flat
from ui import sections as S
from ui.helpers import show
from ui.inputs_form import build_inputs

st.set_page_config(page_title="연료전지·하이브리드 콘덴싱에어컨 사업성 시뮬레이터", page_icon="⚡", layout="wide")
st.title("⚡ 연료전지 + 하이브리드 콘덴싱에어컨 사업성 시뮬레이터")
st.caption("공동주택 1,000세대 · 입력조건 → 월별 에너지 수지 → 연료비 → 매전·매열 수익 → HPS 보상 → 고객 편익 → 연도별 현금흐름 → NPV·IRR → 투자비 회수 가능성")

TABS = ["A 입력조건", "B 월별 Energy Balance", "C 연료전지 사업수지", "D 고객 편익", "E 장기 경제성", "F 최종 결론",
        "G 축열조", "H 그래프", "대수별 비교", "J 추가입력 필요", "검증·Excel", "최종검토 리포트"]
tabs = st.tabs(TABS)

# ── 입력 (탭 A 상단) ──
with tabs[0]:
    inp = build_inputs()

# ── 계산 ──
sweep_df, details = sweep(inp)
n_rec, why, n_heat = recommend(inp, sweep_df)
n = n_rec if inp.n_mode == N_AUTO else int(inp.n_manual)
res = details.get(n) or run_economics(inp, n)
cb_table, cb, cb_month = customer_benefit(inp)
F = S.formula_sets(inp, n, res, cb)

with tabs[0]:
    reg = S.tab_a(inp)
with tabs[1]:
    eff = S.tab_b(inp, n, res, F)
with tabs[2]:
    mb_e, hs, ann_df = S.tab_c(inp, n, res, F)
with tabs[3]:
    S.tab_d(inp, cb_table, cb, cb_month, F)
with tabs[4]:
    S.tab_e(inp, n, res, F)
with tabs[6]:
    storage = S.tab_g(inp, n, F)
with tabs[5]:
    summary = executive_summary(inp, res, cb, storage, n, why if inp.n_mode == N_AUTO else "사용자 수동 지정")
    S.tab_f(summary, n_heat)
report = build_report(inp, n, res, cb, summary, sweep_df, storage)
with tabs[7]:
    S.tab_h(inp, n, res, sweep_df)
with tabs[8]:
    S.tab_units(sweep_df, n_rec, why, n_heat, n)
with tabs[9]:
    miss_df = S.tab_missing(inp)
with tabs[10]:
    st.subheader("기존 검토 결과와의 대조 검증")
    val = validate(inp)
    show(val, dec=3)
    st.caption("입력값을 기본값에서 바꾸면 '불일치'가 나올 수 있으며, 이는 오류가 아니라 입력 변경의 결과입니다.")

    sheets = {
        "01_입력조건": reg,
        "02_열수요환산": demand_table(inp),
        "03_냉방계산": cooling_table(inp),
        "04_월별EnergyBalance": res["bal"],
        "05_종합효율": eff,
        "06_월별사업수지(억원)": mb_e,
        "07_매열내역": hs,
        "08_연간사업수지(억원)": ann_df,
        "09_고객편익": cb_table,
        "10_고객편익_월별": cb_month,
        "11_대수별비교": sweep_df,
        "12_검증": val,
        "13_추가입력필요": miss_df,
        "19_최종검토리포트": report_flat(report),
    }
    if res.get("cf_pre") is not None:
        sheets["14_현금흐름_HPS전(억원)"] = display_cf(res["cf_pre"])
        if res.get("cf_post") is not None:
            sheets["15_현금흐름_HPS후(억원)"] = display_cf(res["cf_post"])
        sheets["16_할인율민감도"] = res["sens"]
        import pandas as pd
        hp = res.get("hps") or {}
        sheets["17_경제성요약"] = pd.DataFrame([{"항목": k, "값": str(v)} for k, v in summary.items() if k not in ("핵심 리스크", "최종 판단")])
    if storage.get("ok"):
        sheets["18_축열조"] = storage["hourly"]
    notes = ["연료전지 + 하이브리드 콘덴싱에어컨 사업성 시뮬레이션 결과",
             f"분석 연료전지 대수: {n}대 / 분석기간 {inp.analysis_years}년 / HPS 목표 IRR {inp.target_irr:.0%} / 기준 할인율 {'미입력' if inp.discount_rate is None else format(inp.discount_rate, '.1%')}",
             "금액 단위: 시트 제목에 '(억원)' 표기된 시트는 억원, 그 외 '(원)' 표기 열은 원",
             "미입력(추가입력 필요) 항목은 0원으로 확정한 것이 아니며, 참고용 모드에서는 계산에서 제외됨",
             "사업자 수익과 고객 편익은 합산하지 않음 / 누적이익과 NPV는 다른 개념"]
    if res.get("excluded"):
        notes.append("계산 제외(미반영) 항목: " + " · ".join(res["excluded"]))
    formulas = []
    for k, lines in F.items():
        formulas.append(f"[{k}]")
        formulas += [ln.replace("`", "") for ln in lines]
    xbytes = build_excel(sheets, formulas, notes)
    st.download_button("📥 Excel 결과 다운로드 (.xlsx)", data=xbytes, file_name="fuelcell_hybrid_simulation_result.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

with tabs[11]:
    S.tab_report(report, n)
