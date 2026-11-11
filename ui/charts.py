"""요청서 H의 그래프 10종 (축·범례·단위 모두 한글, Plotly)."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from sim.constants import MONTH_LABELS


def _bar_layout(fig, title, x, y, barmode=None):
    fig.update_layout(title=title, xaxis_title=x, yaxis_title=y, template="plotly_white")
    if barmode:
        fig.update_layout(barmode=barmode)
    return fig


def demand_by_use(bal):
    f = go.Figure()
    for c, nm in [("난방열", "난방"), ("급탕열", "급탕"), ("냉방용 열", "냉방용 열")]:
        f.add_bar(x=bal["월"], y=bal[c], name=nm)
    return _bar_layout(f, "월별 난방·급탕·냉방 열수요", "월", "열수요 (MWh_th)", "stack")


def demand_vs_gen(bal):
    f = go.Figure()
    f.add_bar(x=bal["월"], y=bal["총 열수요"], name="총 열수요")
    f.add_scatter(x=bal["월"], y=bal["FC 발생열"], name="연료전지 발생열", mode="lines+markers", line=dict(width=3))
    return _bar_layout(f, "월별 총 열수요와 연료전지 발생열 비교", "월", "열량 (MWh_th)")


def used_surplus_short(bal):
    f = go.Figure()
    for c, nm in [("실제 사용열(공급열)", "사용열"), ("잉여열", "잉여열"), ("부족열", "부족열")]:
        f.add_bar(x=bal["월"], y=bal[c], name=nm)
    return _bar_layout(f, "월별 사용열·잉여열·부족열", "월", "열량 (MWh_th)", "group")


def cooling_power(ct):
    f = go.Figure()
    f.add_bar(x=ct["월"], y=ct["일반 냉방 전력(MWh_e)"], name="일반 시스템에어컨")
    f.add_bar(x=ct["월"], y=ct["하이브리드 냉방 전력(MWh_e)"], name="하이브리드 콘덴싱에어컨")
    return _bar_layout(f, "일반 냉방기와 하이브리드 냉방기 전력 비교", "월", "전력사용량 (MWh_e)", "group")


def _years(cf):
    return cf["연도"]


def annual_cf(cf_pre, cf_post=None):
    f = go.Figure()
    f.add_bar(x=_years(cf_pre), y=cf_pre["순현금흐름"] / 1e8, name="HPS 적용 전")
    if cf_post is not None:
        f.add_bar(x=_years(cf_post), y=cf_post["순현금흐름"] / 1e8, name="HPS 적용 후")
    return _bar_layout(f, "연도별 순현금흐름", "연도 (년)", "순현금흐름 (억원)", "group")


def cum_nominal(cf):
    f = go.Figure()
    f.add_scatter(x=_years(cf), y=cf["누적현금흐름"] / 1e8, name="누적 명목 현금흐름", mode="lines+markers")
    f.add_hline(y=0, line_dash="dot")
    return _bar_layout(f, "누적 명목 현금흐름 (초기투자비 차감 후)", "연도 (년)", "누적 현금흐름 (억원)")


def cum_discounted(cf, rates, net):
    """기준 할인율 입력 시 1개, 미입력 시 민감도 4개 곡선."""
    f = go.Figure()
    y = np.arange(len(net))
    for r in rates:
        f.add_scatter(x=y, y=np.cumsum(net / (1 + r) ** y) / 1e8, name=f"할인율 {r:.1%}", mode="lines+markers")
    f.add_hline(y=0, line_dash="dot")
    return _bar_layout(f, "누적 할인현금흐름", "연도 (년)", "누적 할인현금흐름 (억원)")


def hps_before_after(cf_pre, cf_post):
    f = go.Figure()
    f.add_scatter(x=_years(cf_pre), y=cf_pre["누적현금흐름"] / 1e8, name="HPS 적용 전", mode="lines+markers")
    if cf_post is not None:
        f.add_scatter(x=_years(cf_post), y=cf_post["누적현금흐름"] / 1e8, name="HPS 적용 후(IRR 목표)", mode="lines+markers")
    f.add_hline(y=0, line_dash="dot")
    return _bar_layout(f, "HPS 적용 전·후 누적 현금흐름", "연도 (년)", "누적 현금흐름 (억원)")


def npv_sensitivity(sens):
    f = go.Figure()
    x = [f"{r:.1%}" for r in sens["할인율"]]
    f.add_bar(x=x, y=sens["NPV HPS 전(억원)"], name="HPS 적용 전")
    if sens["NPV HPS 후(억원)"].notna().any():
        f.add_bar(x=x, y=sens["NPV HPS 후(억원)"], name="HPS 적용 후")
    return _bar_layout(f, "할인율별 NPV 민감도 (비교구간, 기준 할인율 아님)", "할인율 (%)", "NPV (억원)", "group")


def by_units(df):
    f = go.Figure()
    f.add_scatter(x=df["대수"], y=df["열자가소비율"] * 100, name="열자가소비율", mode="lines+markers")
    f.add_scatter(x=df["대수"], y=df["열폐기율"] * 100, name="열폐기율", mode="lines+markers")
    f.add_scatter(x=df["대수"], y=df["종합효율"] * 100, name="종합효율", mode="lines+markers", line=dict(dash="dash"))
    f.add_hline(y=60, line_dash="dot", annotation_text="종합효율 기준 60%")
    return _bar_layout(f, "연료전지 대수별 열자가소비율 및 열폐기율", "연료전지 대수 (대)", "비율 (%)")
