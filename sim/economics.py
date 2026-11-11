"""장기 경제성 (E): 현금흐름, NPV, IRR, 회수기간, HPS 역산, 할인율 민감도.

금액 단위는 원(내부). 1년차 단가 = 입력단가, 상승률은 2년차부터 (1+g)^(t-1)로 적용.
상승률·비용 등 미입력 항목은 '미반영 목록(excluded)'에 기록하고, 엄격 보류 모드에서는 계산 자체를 보류한다.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from .constants import DISCOUNT_SENSITIVITY
from .energy_balance import energy_balance
from .fuelcell import gas_cost_annual, gen_kwh_annual, heat_sales, opex_year1
from .inputs import ELEC_S1, ELEC_S2, Inputs

# ───────────────────────── 수치해석 도구 ─────────────────────────
def npv(rate: float, cfs) -> float:
    cfs = np.asarray(cfs, float)
    return float(np.sum(cfs / (1.0 + rate) ** np.arange(len(cfs))))


def bisect(f: Callable[[float], float], lo: float, hi: float, tol: float = 1e-12, it: int = 300) -> Optional[float]:
    flo, fhi = f(lo), f(hi)
    if np.isnan(flo) or np.isnan(fhi) or flo * fhi > 0:
        return None
    for _ in range(it):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if flo * fm <= 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
        if abs(hi - lo) < tol * max(1.0, abs(mid)):
            break
    return 0.5 * (lo + hi)


def irr(cfs) -> Optional[float]:
    cfs = np.asarray(cfs, float)
    if not (cfs.min() < 0 < cfs.max()):
        return None
    f = lambda r: npv(r, cfs)
    lo, hi = -0.95, 0.5
    while f(lo) * f(hi) > 0 and hi < 100:
        hi = hi * 2
    return bisect(f, lo, hi)


def payback(cum: np.ndarray) -> Optional[dict]:
    """누적현금흐름이 처음 0 이상이 되는 시점. 분석기간 내 미회수면 None (연수 임의 산정 금지)."""
    for k in range(1, len(cum)):
        if cum[k] >= 0:
            frac = (k - 1) + (-cum[k - 1]) / (cum[k] - cum[k - 1]) if cum[k] != cum[k - 1] else k
            return {"year": k, "interp": frac}
    return None


def solve_hps(base_cf: np.ndarray, target: float, unit: np.ndarray) -> Optional[float]:
    """NPV(target; base + H·unit) = 0 이 되는 H를 이분법으로 역산 (IRR = target)."""
    f = lambda h: npv(target, base_cf + h * unit)
    a, b = -1e10, 1e10
    while f(a) * f(b) > 0 and b < 1e18:
        a, b = a * 10, b * 10
    return bisect(f, a, b)


# ───────────────────────── 현금흐름 ─────────────────────────
def price_scenario(inp: Inputs):
    """(HPS 적용 전 기준단가, 220 포함단가, 비고)"""
    if inp.elec_mode == ELEC_S1:
        return inp.elec_price_220, None, "220원/kWh = 일반 매전단가. HPS는 이 위에 별도 가산(역산)."
    return inp.elec_price_base, inp.elec_price_220, "220원/kWh = 매전+HPS 포함. HPS 별도 가산 없음. 기준단가는 일반 매전단가 입력값."


def build_cashflow(inp: Inputs, n: int, bal: pd.DataFrame, hs: pd.DataFrame, price: float,
                   hps_const: float = 0.0, hps_per_kwh: float = 0.0):
    """연도별 현금흐름(원). 반환: (DataFrame, 미반영 항목 리스트)"""
    Y = inp.analysis_years
    t = np.arange(Y + 1)
    ex: List[str] = []

    def esc(rate, label):
        if rate is None:
            ex.append(f"{label} (불변단가로 계산)")
            rate = 0.0
        return np.where(t >= 1, (1 + rate) ** np.maximum(t - 1, 0), 0.0)

    e_gas, e_elec = esc(inp.gas_escalation, "가스가격 상승률"), esc(inp.elec_escalation, "전력가격 상승률")
    e_heat, e_inf = esc(inp.heat_escalation, "열가격 상승률"), esc(inp.inflation, "물가상승률")
    one = (t >= 1).astype(float)

    gen1 = gen_kwh_annual(inp, n)
    deg = inp.deg_rate
    gen_t = np.where(t >= 1, gen1 * (1 - deg) ** np.maximum(t - 1, 0), 0.0)

    heat1 = hs["매열수익(원)"]
    if heat1.isna().any():
        ex.append("지역난방 월별 열요금 (매열수익 일부/전부 미반영)")
    heat1 = float(heat1.fillna(0).sum())

    ox = opex_year1(inp, n)
    def get(k):
        v = ox[k]
        if v is None:
            ex.append(f"{k} 미반영")
            return 0.0
        return v

    capex = np.zeros(Y + 1); capex[0] = -inp.fc_capex * n
    support = np.zeros(Y + 1)
    if inp.subsidy is None and inp.tax_credit is None:
        ex.append("정부보조금·세액공제 미반영")
    if inp.subsidy:
        support[0] += inp.subsidy
    if inp.tax_credit and 0 <= inp.tax_credit_year <= Y:
        support[inp.tax_credit_year] += inp.tax_credit

    stack = np.zeros(Y + 1)
    if inp.stack_interval is None or inp.stack_cost is None:
        ex.append("스택 교체주기·교체비 미반영")
    elif inp.stack_interval > 0:
        k = inp.stack_interval
        while k < Y:
            stack[int(round(k))] -= inp.stack_cost * n * e_inf[int(round(k))]
            k += inp.stack_interval

    final = np.zeros(Y + 1); decom = np.zeros(Y + 1)
    if inp.salvage is None:
        ex.append("잔존가치 미반영")
    else:
        final[Y] += inp.salvage * n
    if inp.decom is None:
        ex.append("철거비 미반영")
    else:
        decom[Y] -= inp.decom * n * e_inf[Y]

    elec_rev = gen_t * price * e_elec
    hps = one * hps_const + gen_t * hps_per_kwh
    cf = pd.DataFrame({
        "연도": t,
        "초기투자비": capex,
        "정부보조·세액공제": support,
        "가스비": -gas_cost_annual(inp, n) * e_gas,
        "O&M·LTSA": -get("O&M·LTSA") * e_inf,
        "스택교체비": stack,
        "보조동력비": -get("보조동력비") * e_inf,
        "보험·제세공과금": -get("보험·제세공과금") * e_inf,
        "기타 운영비": -get("기타 운영비") * e_inf,
        "철거비": decom,
        "잔존가치": final,
        "매전수익": elec_rev,
        "매열수익": heat1 * e_heat,
        "HPS": hps,
    })
    cols = [c for c in cf.columns if c != "연도"]
    cf["순현금흐름"] = cf[cols].sum(axis=1)
    cf["누적현금흐름"] = cf["순현금흐름"].cumsum()
    return cf, list(dict.fromkeys(ex))


def add_discount(cf: pd.DataFrame, rate: Optional[float]) -> pd.DataFrame:
    cf = cf.copy()
    if rate is None:
        cf["할인현금흐름"] = np.nan
        cf["누적할인현금흐름"] = np.nan
    else:
        cf["할인현금흐름"] = cf["순현금흐름"] / (1 + rate) ** cf["연도"]
        cf["누적할인현금흐름"] = cf["할인현금흐름"].cumsum()
    return cf


def display_cf(cf: pd.DataFrame) -> pd.DataFrame:
    """요청서 E-3 형식(억원). O&M 열은 운영비 전체 합, 기타는 지원금·철거·잔존."""
    e = 1e8
    d = pd.DataFrame({
        "연도": cf["연도"],
        "초기투자비": cf["초기투자비"] / e,
        "가스비": cf["가스비"] / e,
        "O&M(운영비 합)": (cf["O&M·LTSA"] + cf["스택교체비"] + cf["보조동력비"] + cf["보험·제세공과금"] + cf["기타 운영비"]) / e,
        "매전수익": cf["매전수익"] / e,
        "매열수익": cf["매열수익"] / e,
        "HPS": cf["HPS"] / e,
        "기타(지원금·철거·잔존)": (cf["정부보조·세액공제"] + cf["철거비"] + cf["잔존가치"]) / e,
        "순현금흐름": cf["순현금흐름"] / e,
        "할인현금흐름": cf["할인현금흐름"] / e,
        "누적현금흐름": cf["누적현금흐름"] / e,
        "누적할인현금흐름": cf["누적할인현금흐름"] / e,
    })
    return d


def checkpoints(inp: Inputs, cf: pd.DataFrame) -> pd.DataFrame:
    """12·15·20년 시점 누적값. 누적이익(투자비 차감 후)과 NPV를 혼용하지 않도록 분리 표기."""
    Y = inp.analysis_years
    pts = sorted({p for p in (12, 15, Y) if p <= Y})
    rows = []
    for p in pts:
        r = cf[cf["연도"] == p].iloc[0]
        cum = r["누적현금흐름"]
        opc = cf[(cf["연도"] >= 1) & (cf["연도"] <= p)]["순현금흐름"].sum()
        cumd = r["누적할인현금흐름"]
        rows.append({
            "평가시점": f"{p}년", "누적 운영현금흐름(투자비 제외, 억원)": opc / 1e8,
            "누적 명목 현금흐름(투자비 차감, 억원)": cum / 1e8,
            "누적 할인현금흐름(억원)": cumd / 1e8,
            "초기투자비 회수 여부(명목)": "회수" if cum >= 0 else "미회수",
            "초기투자비 회수 여부(할인)": "기준 할인율 미입력" if np.isnan(cumd) else ("회수" if cumd >= 0 else "미회수"),
        })
    return pd.DataFrame(rows)


def _pb_text(pb, Y):
    return f"{pb['interp']:.1f}년 (연도기준 {pb['year']}년차)" if pb else f"분석기간 {Y}년 내 미회수"


def metrics(inp: Inputs, cf: pd.DataFrame, rate: Optional[float]) -> dict:
    Y = inp.analysis_years
    net = cf["순현금흐름"].to_numpy()
    out = {"irr": irr(net), "payback": payback(np.cumsum(net)), "sum_operating": float(net[1:].sum())}
    out["payback_text"] = _pb_text(out["payback"], Y)
    if rate is None:
        out.update(npv=None, dpayback=None, dpayback_text="기준 할인율 미입력")
    else:
        d = net / (1 + rate) ** np.arange(len(net))
        out["npv"] = float(d.sum())
        out["dpayback"] = payback(np.cumsum(d))
        out["dpayback_text"] = _pb_text(out["dpayback"], Y)
    return out


def sensitivity(inp: Inputs, cf_pre: Optional[pd.DataFrame], cf_post: Optional[pd.DataFrame]) -> pd.DataFrame:
    """할인율별 NPV 민감도. 비교구간이며 기준 할인율을 확정한 것이 아니다."""
    Y = inp.analysis_years
    rates = list(DISCOUNT_SENSITIVITY)
    if inp.discount_rate is not None and all(abs(inp.discount_rate - r) > 1e-9 for r in rates):
        rates.append(inp.discount_rate)
    rows = []
    for r in sorted(rates):
        row = {"할인율": r, "구분": "기준 할인율" if inp.discount_rate is not None and abs(r - inp.discount_rate) < 1e-9 else "민감도 비교구간"}
        for tag, cf in (("HPS 전", cf_pre), ("HPS 후", cf_post)):
            if cf is None:
                row[f"NPV {tag}(억원)"] = np.nan; row[f"할인회수기간 {tag}"] = "산정 불가"
                continue
            net = cf["순현금흐름"].to_numpy()
            d = net / (1 + r) ** np.arange(len(net))
            row[f"NPV {tag}(억원)"] = d.sum() / 1e8
            row[f"할인회수기간 {tag}"] = _pb_text(payback(np.cumsum(d)), Y)
        rows.append(row)
    return pd.DataFrame(rows)


# ───────────────────────── 통합 실행 ─────────────────────────
def run_economics(inp: Inputs, n: int) -> dict:
    """연료전지 n대 기준 전체 경제성 계산."""
    bal = energy_balance(inp, n)
    hs = heat_sales(inp, bal)
    p_pre, p_bundled, p_note = price_scenario(inp)
    Y = inp.analysis_years
    gen1 = gen_kwh_annual(inp, n)
    res = {"n": n, "bal": bal, "hs": hs, "price_note": p_note, "price_pre": p_pre, "price_bundled": p_bundled,
           "gen_kwh": gen1, "status": "ok", "excluded": []}

    # 미반영 점검(가격과 무관) — 기준 현금흐름으로 확인
    cf_chk, ex = build_cashflow(inp, n, bal, hs, p_pre if p_pre is not None else inp.elec_price_220)
    res["excluded"] = ex
    if inp.strict_hold and (ex or inp.discount_rate is None or not inp.elec_mode_confirmed):
        res["status"] = "hold"
        res["hold_reason"] = ex + (["기준 할인율 미입력"] if inp.discount_rate is None else []) + \
                             ([] if inp.elec_mode_confirmed else ["220원/kWh 해석 미확인"])
        return res
    if ex:
        res["status"] = "partial"

    target = inp.target_irr
    # ── HPS 적용 전 ──
    if p_pre is None:
        res.update(cf_pre=None, m_pre=None, hps=None, cf_post=None, m_post=None)
    else:
        cf_pre, _ = build_cashflow(inp, n, bal, hs, p_pre)
        cf_pre = add_discount(cf_pre, inp.discount_rate)
        res["cf_pre"], res["m_pre"] = cf_pre, metrics(inp, cf_pre, inp.discount_rate)
        base = cf_pre["순현금흐름"].to_numpy()
        yrs = np.arange(Y + 1)
        unit_const = (yrs >= 1).astype(float)
        deg = inp.deg_rate
        unit_kwh = np.where(yrs >= 1, gen1 * (1 - deg) ** np.maximum(yrs - 1, 0), 0.0)
        H = solve_hps(base, target, unit_const)           # 연간 정액 HPS (원/년)
        h = solve_hps(base, target, unit_kwh)             # 발전량 비례 HPS (원/kWh)
        hps = {"irr_before": res["m_pre"]["irr"], "target": target}
        if H is None or h is None:
            hps.update(H=None, h=None, note="HPS 역산 실패(수렴 범위 내 해 없음)")
            res.update(hps=hps, cf_post=None, m_post=None)
        else:
            needed = H > 0
            Hc, hc = max(H, 0.0), max(h, 0.0)
            cf_post, _ = build_cashflow(inp, n, bal, hs, p_pre, hps_const=Hc)
            cf_post = add_discount(cf_post, inp.discount_rate)
            cf_post_kwh, _ = build_cashflow(inp, n, bal, hs, p_pre, hps_per_kwh=hc)
            cf_post_kwh = add_discount(cf_post_kwh, inp.discount_rate)
            m_post = metrics(inp, cf_post, inp.discount_rate)
            hps.update(H=Hc, h_const_equiv=Hc / gen1 if gen1 else np.nan, h=hc, H_kwh_equiv_y1=hc * gen1,
                       needed=needed, irr_after=m_post["irr"], irr_after_kwh=irr(cf_post_kwh["순현금흐름"].to_numpy()),
                       note="" if needed else "HPS 적용 전에도 IRR이 목표 이상 → HPS 불필요")
            res.update(hps=hps, cf_post=cf_post, cf_post_kwh=cf_post_kwh, m_post=m_post)
        res["sens"] = sensitivity(inp, res["cf_pre"], res.get("cf_post"))
    if p_pre is None:
        res["sens"] = sensitivity(inp, None, None)

    # 220원 포함단가(S2) 현금흐름
    if p_bundled is not None and inp.elec_mode == ELEC_S2:
        cf_b, _ = build_cashflow(inp, n, bal, hs, p_bundled)
        cf_b = add_discount(cf_b, inp.discount_rate)
        res["cf_bundled"], res["m_bundled"] = cf_b, metrics(inp, cf_b, inp.discount_rate)
    return res
