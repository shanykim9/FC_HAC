"""F. 최종 결론(경영진 요약) 생성. 모든 문구는 계산 결과에서 파생하며 임의 수치를 만들지 않는다."""
from __future__ import annotations

import numpy as np

from .efficiency import annual_total_efficiency
from .fuelcell import gas_cost_hourly
from .inputs import ELEC_S1, Inputs


def _pct(x):
    return "산정 불가" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x*100:.2f}%"


def _eok(x):
    return "산정 불가" if x is None else f"{x/1e8:,.2f}억원"


def executive_summary(inp: Inputs, res: dict, cb: dict, storage: dict, n: int, rec_note: str) -> dict:
    bal = res["bal"]
    eta = annual_total_efficiency(inp, bal)
    missing = inp.missing_items()
    blocking = [m for m in missing if m["경제성 계산 영향"] == "예"]
    out = {}
    m_pre, m_post, hps = res.get("m_pre"), res.get("m_post"), res.get("hps")

    # 경제성 판정 (계산 가정: 판정 규칙은 아래와 같음)
    if res["status"] == "hold" or m_pre is None:
        verdict = "판정 보류 (추가입력 필요)"
    elif blocking:
        verdict = f"판정 보류 (미확정 입력 {len(blocking)}건) — 참고: " + (
            "HPS 적용 전 IRR이 목표 이상(미반영 비용 제외 상한 기준)" if (m_pre["irr"] or -1) >= inp.target_irr
            else "HPS 없이는 목표 IRR 미달(미반영 비용 제외 상한 기준)")
    elif (m_pre["irr"] or -1) >= inp.target_irr:
        verdict = "사업성 있음"
    elif m_pre["irr"] is not None and m_pre["irr"] > 0:
        verdict = "조건부 있음 (HPS 보상 필요)"
    else:
        verdict = "부족 (HPS 없이는 투자비 미회수)"
    out["경제성"] = verdict
    out["HPS 적용 전 IRR"] = _pct(m_pre["irr"]) if m_pre else "산정 불가"
    out["HPS 적용 후 IRR"] = _pct(hps["irr_after"]) if hps and hps.get("irr_after") is not None else "산정 불가"
    out["기준 할인율 NPV"] = (f"{inp.discount_rate:.1%} 기준 HPS 전 {_eok(m_pre['npv'])} / HPS 후 {_eok(m_post['npv']) if m_post else '산정 불가'}"
                          if m_pre and m_pre["npv"] is not None else "기준 할인율 미입력 → 민감도표 참조")
    out["단순 투자회수기간"] = f"HPS 전 {m_pre['payback_text']} / HPS 후 {m_post['payback_text'] if m_post else '산정 불가'}" if m_pre else "산정 불가"
    out["할인 투자회수기간"] = f"HPS 전 {m_pre['dpayback_text']} / HPS 후 {m_post['dpayback_text'] if m_post else '산정 불가'}" if m_pre else "산정 불가"
    if hps and hps.get("H") is not None:
        txt = f"연간 {hps['H']/1e8:,.2f}억원, {hps['h']:,.1f}원/kWh (목표 IRR {inp.target_irr:.0%} 역산)"
        p_base = res.get("price_pre")
        if p_base is not None:
            # 220원/kWh를 일반 매전단가로 해석한 경우(기본): 기존 220원/kWh에 필요 HPS를 합산한 총 단가를 병기
            label = "기존 HPS" if inp.elec_mode == ELEC_S1 else "일반 매전단가"
            txt += f"에 {label} {p_base:,.0f}원/kWh 합산하여 총 {p_base + hps['h']:,.1f}원/kWh"
        out["필요 HPS"] = txt
    else:
        out["필요 HPS"] = "산정 불가 (일반 매전단가 입력 필요 등)"
    out["연간 고객편익"] = f"{cb['net_won']/1e8:,.2f}억원 (세대당 {cb['net_per_hh_won']/1e4:,.1f}만원) — 사업자 수익과 합산하지 않음"
    out["종합효율 60% 충족 여부"] = f"{'충족' if eta >= 0.60 else '미충족'} (연간 {eta:.1%})"
    out["적정 연료전지 대수"] = f"{n}대 (분석 기준) — {rec_note}"
    out["축열조 용량"] = (f"{storage['q_design']:,.2f} MWh_th (약 {storage['volume_m3']:,.0f} ㎥)" if storage.get("ok") else "추가입력 필요 (시간별 자료 없음)")
    short = float(bal["부족열"].sum())
    aux = f"{short:,.0f} MWh_th/년"
    if inp.aux_heat_eff and inp.aux_heat_price and inp.aux_heat_type:
        aux += f" ({inp.aux_heat_type}, 에너지 소요 약 {short/inp.aux_heat_eff:,.0f} MWh)"
    out["보조열원 필요량"] = aux

    # 핵심 리스크 3가지 (계산값 기반)
    spark = gas_cost_hourly(inp) / inp.fc_elec_kw
    p_pre = res.get("price_pre")
    risks = [f"발전원가(가스비 {spark:,.1f}원/kWh_e)와 매전단가({'미입력' if p_pre is None else f'{p_pre:,.1f}원/kWh'})의 역마진 — 가스·전력가격 상승률 미확정",
             f"열수요 대비 열 이용: 열폐기율 {bal['잉여열'].sum()/bal['FC 발생열'].sum():.1%}, 부족열 {short:,.0f} MWh_th — 봄·가을 잉여열은 수익 0원",
             f"미확정 입력 {len(blocking)}건(O&M·스택교체·상승률·보조금·잔존/철거 등)으로 현금흐름이 과대/과소 평가될 수 있음"]
    out["핵심 리스크"] = risks

    # 최종 판단 3~5줄
    lines = []
    if m_pre is None:
        lines.append("경제성 계산이 보류되어 현재 정량 판단 불가 — 추가입력 필요 항목을 먼저 확정해야 함.")
    else:
        lines.append(f"{n}대 기준 HPS 적용 전 IRR은 {out['HPS 적용 전 IRR']}, 목표 IRR {inp.target_irr:.0%} 달성에 필요한 HPS는 {out['필요 HPS']}.")
        lines.append(f"종합효율은 연간 {eta:.1%}로 60% 기준 {'충족' if eta >= .6 else '미충족'}, 열폐기율 {bal['잉여열'].sum()/bal['FC 발생열'].sum():.1%}.")
    lines.append(f"고객 순편익 연 {cb['net_won']/1e8:,.2f}억원은 별도 지표이며 사업자 IRR/NPV에 합산하지 않음.")
    if blocking:
        lines.append(f"추가입력 필요 {len(blocking)}건이 남아 있어 본 결과는 '미반영 항목 제외' 조건부 결과이며 투자 판단 근거로 확정 불가.")
    out["최종 판단"] = lines
    return out
