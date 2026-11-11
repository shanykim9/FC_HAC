"""Streamlit 공통 표시 도우미 (버전별 width 인자 차이 흡수)."""
from __future__ import annotations

import pandas as pd
import streamlit as st


def _call(fn, *a, **kw):
    try:
        return fn(*a, width="stretch", **kw)
    except TypeError:
        return fn(*a, use_container_width=True, **kw)


def show(df: pd.DataFrame, dec: int = 1, per_col: dict | None = None, pct_cols=(), key=None):
    """숫자 서식(천단위, 소수자리, NaN='—')을 적용해 표시."""
    per_col = per_col or {}
    fm = {}
    for c in df.columns:
        if c in pct_cols:
            fm[c] = "{:.1%}"
        elif pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c]):
            fm[c] = f"{{:,.{per_col.get(c, dec)}f}}"
    _call(st.dataframe, df.style.format(fm, na_rep="—"), hide_index=True)


def plot(fig, key=None):
    fig.update_layout(font=dict(family="Malgun Gothic, Apple SD Gothic Neo, Noto Sans KR, sans-serif", size=13),
                      margin=dict(l=10, r=10, t=50, b=10), legend=dict(orientation="h", y=-0.2))
    _call(st.plotly_chart, fig, key=key)


def formula_box(title: str, lines: list[str]):
    """결과표 바로 아래에 계산식·단위변환 과정을 표시."""
    with st.expander(f"🧮 계산식·단위변환 — {title}", expanded=True):
        for ln in lines:
            st.markdown(ln)


def warn_excluded(excluded: list[str], status: str):
    if status == "hold":
        st.error("엄격 보류 모드: 미입력 항목이 있어 경제성 계산을 보류했습니다. → 추가입력 필요 항목 탭 확인")
    elif excluded:
        st.warning("**조건부(참고용) 결과** — 아래 항목은 0원으로 확정한 것이 아니라 *미입력이라 계산에서 제외*되었습니다: "
                   + " · ".join(excluded))


def eok(x):
    return None if x is None else x / 1e8
