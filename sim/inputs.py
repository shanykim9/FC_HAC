"""모든 입력값을 담는 Inputs 데이터클래스.

원칙: 요청서에서 값이 주어진 항목만 기본값을 넣고, '추가입력 필요' 항목은 None으로 둔다.
None은 0이 아니라 '미입력'을 의미하며, 계산 모듈이 미반영 항목 목록으로 추적한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from .constants import (DAYS_IN_MONTH, DEFAULT_DISCOUNT_RATE, DEFAULT_DISTRICT_HEAT_PRICE_MCAL, DEFAULT_TARGET_IRR, DEFAULT_HEFLH, DEFAULT_SEASON_MAP, DHW_130,
                        HEAT_PRICE_UNITS, HEATING_130, MONTH_LABELS)

# 선택지 문자열
ELEC_S1 = "220원/kWh = 일반 매전단가 (HPS는 별도 가산·역산)"
ELEC_S2 = "220원/kWh = 매전단가+HPS 포함 (HPS 별도 가산 없음)"
GAS_VAT_UNKNOWN = "미확인 (입력단가 그대로 사용)"
GAS_VAT_INCL = "입력단가에 부가세 포함됨"
GAS_VAT_EXCL = "입력단가는 부가세 별도 (가산)"
N_AUTO = "자동 추천(참고)"
N_MANUAL = "수동 지정"
OEM_PER_UNIT = "원/년/대"
OEM_PER_KWH = "원/kWh"

ELEC_COMPONENT_KEYS = ["전력량요금", "기후환경요금", "연료비조정요금", "부가가치세", "전력산업기반기금"]
WATER_COMPONENT_KEYS = ["상수도요금", "하수도요금", "물이용부담금"]


@dataclass
class Inputs:
    # ── 분석 설정 ──
    strict_hold: bool = False           # True: 미입력 항목이 있으면 경제성 계산 보류
    n_mode: str = N_AUTO
    n_manual: int = 2
    n_max: int = 10
    target_irr: float = DEFAULT_TARGET_IRR      # HPS 역산 목표 IRR (이 IRR이 되도록 필요 HPS 역산)
    discount_rate: Optional[float] = DEFAULT_DISCOUNT_RATE
    # ── A-1 공동주택 ──
    households: float = 1000
    ref_households: float = 130
    area_target_m2: float = 112.4
    area_ref_m2: float = 59.0
    persons_target: float = 4.0
    persons_ref: float = 4.0
    persons_ref_confirmed: bool = True
    analysis_years: int = 20
    region: str = "수도권"
    # ── A-2 실측자료 [Mcal/월] ──
    heating_130: List[float] = field(default_factory=lambda: list(HEATING_130))
    dhw_130: List[float] = field(default_factory=lambda: list(DHW_130))
    season_map: List[str] = field(default_factory=lambda: list(DEFAULT_SEASON_MAP))
    # ── A-3 냉방부하 ──
    cool_w_per_m2: float = 59.2
    cool_area_m2: float = 84.8
    sw_ratio: float = 0.60
    sw_factor: float = 1.08
    se_factor: float = 1.02
    cop_normal: float = 3.5
    cop_hyb_e: float = 5.2
    cop_hyb_h: float = 1.7
    heflh: List[float] = field(default_factory=lambda: list(DEFAULT_HEFLH))
    # ── A-4 하이브리드 콘덴싱에어컨 ──
    hyb_cool_kw: float = 11.0
    hyb_elec_kw: float = 2.1
    hyb_heat_kw: float = 6.0
    water_lpm: float = 1.1
    water_partload_factor: Optional[float] = None   # 부분부하 증발수 보정(비례 대비 배수), 추가입력 필요
    # ── A-5 연료전지 ──
    fc_elec_kw: float = 400.0
    fc_heat_kw: float = 446.0
    fc_gas_mj_h: float = 3798.2
    fc_util: float = 0.95
    fc_capex: float = 2.5e9
    # ── A-6 도시가스 ──
    gas_price: float = 25.0573
    gas_vat_mode: str = GAS_VAT_EXCL
    gas_vat_rate: float = 0.10
    gas_escalation: Optional[float] = None
    # ── A-7 전력 매전 ──
    elec_mode: str = ELEC_S1
    elec_mode_confirmed: bool = True
    elec_price_220: float = 220.0
    elec_price_base: Optional[float] = None     # '220에 HPS 포함' 선택 시 필요한 일반 매전단가
    elec_escalation: Optional[float] = None
    # ── A-8 열 판매 ──
    heat_price_unit: str = "원/Mcal"
    # 기본값: 한국지역난방공사 동절기 열요금 115.59 원/Mcal (동절기 월만 입력, 나머지는 매열 대상 아님)
    district_heat_price: List[Optional[float]] = field(default_factory=lambda: list(DEFAULT_DISTRICT_HEAT_PRICE_MCAL))
    fc_heat_price_ratio: float = 0.70
    heat_sale_seasons: List[str] = field(default_factory=lambda: ["동절기"])
    heat_escalation: Optional[float] = None
    pipe_loss: Optional[float] = None
    # ── A-9 고객 요금 ──
    elec_eff_price: float = 211.9
    use_elec_components: bool = False
    elec_components: Dict[str, Optional[float]] = field(default_factory=lambda: {k: None for k in ELEC_COMPONENT_KEYS})
    water_price: float = 1230.0
    use_water_components: bool = False
    water_components: Dict[str, Optional[float]] = field(default_factory=lambda: {k: None for k in WATER_COMPONENT_KEYS})
    # ── 비용·경제성 변수 (추가입력 필요) ──
    inflation: Optional[float] = None
    oem_value: Optional[float] = None
    oem_unit: str = OEM_PER_UNIT
    stack_interval: Optional[float] = None
    stack_cost: Optional[float] = None
    aux_kw: Optional[float] = None
    aux_price: Optional[float] = None
    insurance: Optional[float] = None       # 원/년/대
    other_opex: Optional[float] = None      # 원/년 (사업 전체)
    subsidy: Optional[float] = None         # 원 (0년차 총액)
    tax_credit: Optional[float] = None      # 원 (총액)
    tax_credit_year: int = 1
    salvage: Optional[float] = None         # 원/대 (최종연도)
    decom: Optional[float] = None           # 원/대 (최종연도)
    degradation_on: bool = False            # 체크 시에만 성능저하 반영
    degradation: Optional[float] = None     # 연간 발전량 감소율
    summer_surplus_tol: float = 0.0         # 하절기 허용 잉여열 비율(축열조 저장 허용분)
    # ── 보조열원 (결론용, 사업자 현금흐름 미포함) ──
    aux_heat_type: str = ""
    aux_heat_eff: Optional[float] = None
    aux_heat_price: Optional[float] = None  # 원/kWh(에너지)

    # ── 파생값 ──
    @property
    def heating_factor(self) -> float:
        return (self.households / self.ref_households) * (self.area_target_m2 / self.area_ref_m2)

    @property
    def dhw_factor(self) -> float:
        return (self.households / self.ref_households) * (self.persons_target / self.persons_ref)

    @property
    def deg_rate(self) -> float:
        return float(self.degradation) if (self.degradation_on and self.degradation is not None) else 0.0

    @property
    def hours(self) -> List[int]:
        return [d * 24 for d in DAYS_IN_MONTH]

    @property
    def hours_year(self) -> int:
        return sum(self.hours)

    def gas_price_eff(self) -> float:
        if self.gas_vat_mode == GAS_VAT_EXCL:
            return self.gas_price * (1 + self.gas_vat_rate)
        return self.gas_price

    def elec_price_eff(self):
        """(단가, 비고)"""
        if self.use_elec_components:
            vals = list(self.elec_components.values())
            if all(v is not None for v in vals):
                return float(sum(vals)), "항목별 입력 합계"
            return self.elec_eff_price, "항목 입력 미완성 → 실효단가 직접입력값 사용"
        return self.elec_eff_price, "실효단가 직접 입력"

    def water_price_eff(self):
        if self.use_water_components:
            vals = list(self.water_components.values())
            if all(v is not None for v in vals):
                return float(sum(vals)), "항목별 입력 합계"
            return self.water_price, "항목 입력 미완성 → 총단가 직접입력값 사용"
        return self.water_price, "총단가 직접 입력"

    def heat_price_mwh(self, i: int) -> Optional[float]:
        """지역난방 월별 열요금 → 원/MWh_th (미입력이면 None)."""
        p = self.district_heat_price[i]
        if p is None or p != p:
            return None
        return p * HEAT_PRICE_UNITS[self.heat_price_unit]

    def fc_heat_price_mwh(self, i: int) -> Optional[float]:
        p = self.heat_price_mwh(i)
        return None if p is None else p * self.fc_heat_price_ratio

    # ── 미입력 항목 점검 ──
    def missing_items(self) -> List[dict]:
        m: List[dict] = []

        def add(label, impact, blocking=True):
            m.append({"항목": label, "영향": impact, "경제성 계산 영향": "예" if blocking else "아니오"})

        if self.discount_rate is None:
            add("기준 할인율", "단일 NPV·할인회수기간 확정 불가 → 3/5/7/10% 민감도만 제공", True)
        if not self.elec_mode_confirmed:
            add("220원/kWh의 성격 확인 (매전단가 vs HPS 포함)", "HPS 중복계상 방지 — 해석 확인 필요", True)
        if self.elec_mode == ELEC_S2 and self.elec_price_base is None:
            add("일반 전력 매전단가 (HPS 제외)", "HPS 적용 전 IRR·필요 HPS 산정 불가", True)
        if self.gas_vat_mode == GAS_VAT_UNKNOWN:
            add("도시가스 단가의 부가세 포함 여부", "가스비 ±10% 가능", True)
        if not self.persons_ref_confirmed:
            add("Reference 130세대 실제 평균 거주인원(3명 가정) 확인", "급탕 환산계수 변동", True)
        if any(self.heat_price_mwh(i) is None for i in range(12) if self.season_map[i] in self.heat_sale_seasons):
            add("지역난방 월별 열요금 (매열 대상 월)", "매열수익 미반영", True)
        if self.oem_value is None:
            add("O&M·LTSA 비용", "운영비 미반영", True)
        if self.stack_interval is None or self.stack_cost is None:
            add("스택 교체주기·교체비", "스택 교체비 미반영", True)
        if self.aux_kw is None or self.aux_price is None:
            add("연료전지 보조동력(kW/대) 및 적용 전력단가", "보조동력비 미반영", True)
        if self.insurance is None:
            add("보험료 및 제세공과금", "미반영", True)
        if self.other_opex is None:
            add("기타 운영비", "미반영", True)
        for lab, v in [("가스가격 상승률", self.gas_escalation), ("전력가격 상승률", self.elec_escalation),
                       ("열가격 상승률", self.heat_escalation), ("물가상승률", self.inflation)]:
            if v is None:
                add(lab, "상승률 미적용(불변단가)으로 계산", True)
        if self.subsidy is None and self.tax_credit is None:
            add("정부보조금 및 세액공제", "미반영", True)
        if self.salvage is None:
            add("잔존가치", "미반영", True)
        if self.decom is None:
            add("철거비", "미반영", True)
        if self.pipe_loss is None:
            add("열배관 손실률", "배관손실 미반영(손실 0%로 계산한 것이 아님)", True)
        if self.degradation_on and self.degradation is None:
            add("연간 발전량 감소율(성능저하 반영 체크됨)", "성능저하 미반영", True)
        if self.water_partload_factor is None:
            add("하이브리드 냉방 부분부하 성능·부분부하별 증발수량", "증발수량은 냉방열 비례 기본 시나리오만 계산", False)
        add("축열조 충·방열효율, Peak-day 시간별 냉방·급탕부하 등", "축열조 용량 산정 (G탭 입력 시 계산)", False)
        if self.aux_heat_eff is None or self.aux_heat_price is None or not self.aux_heat_type:
            add("보조열원 종류·효율·에너지단가", "보조열원 필요량(MWh_th)만 표시, 비용 미산정", False)
        return m


def input_register(inp: Inputs) -> pd.DataFrame:
    """A. 입력조건 및 가정 — 모든 입력값, 출처, 구분을 한 표로."""
    rows = []
    C, MEAS, REF, ASM, NEED, CHK = "확정값(작업요청서)", "실측자료", "기존 검토 Reference", "계산 가정", "추가입력 필요", "확인 필요"

    def r(group, name, val, unit, src, note=""):
        if val is None:
            val, src = "미입력", NEED
        rows.append({"구분": group, "항목": name, "입력값": val, "단위": unit, "출처/상태": src, "비고": note})

    g = "A-1 공동주택"
    r(g, "세대수", inp.households, "세대", C)
    r(g, "분석 대상 평형 환산면적", inp.area_target_m2, "㎡", C, "34평형")
    r(g, "Reference 전용면적", inp.area_ref_m2, "㎡", C)
    r(g, "Reference 세대수", inp.ref_households, "세대", C)
    r(g, "난방 면적 보정계수", round(inp.area_target_m2 / inp.area_ref_m2, 4), "-", ASM, "= 112.4 ÷ 59")
    r(g, "분석 대상 거주인원", inp.persons_target, "인/세대", C)
    r(g, "Reference 거주인원", inp.persons_ref, "인/세대", C if inp.persons_ref_confirmed else CHK, "사용자 지정 가정(4명)")
    r(g, "급탕 인원 보정계수", round(inp.persons_target / inp.persons_ref, 4), "-", ASM, "= 대상 인원 ÷ Reference 인원 (면적비 보정 아님)")
    r(g, "분석기간", inp.analysis_years, "년", C)
    r(g, "기준 지역", inp.region, "-", C)
    r(g, "계절 구분(월별)", " / ".join(f"{i+1}월:{s}" for i, s in enumerate(inp.season_map)), "-", ASM)
    g = "A-2 실측"
    r(g, "난방·급탕 월별 실측(130세대)", "UI 표 참조", "Mcal/월", MEAS)
    r(g, "열량 환산", "1 MWh = 860 Mcal, 1 MWh = 3.6 GJ", "-", C)
    g = "A-3 냉방부하"
    for n_, v, u in [("세대당 기준 냉방부하", inp.cool_w_per_m2, "W/㎡"), ("냉방 적용면적", inp.cool_area_m2, "㎡"),
                     ("남서향 비율", inp.sw_ratio, "-"), ("남서향 보정계수", inp.sw_factor, "-"),
                     ("남동향 보정계수", inp.se_factor, "-"), ("일반 시스템에어컨 COP", inp.cop_normal, "-"),
                     ("하이브리드 전기 COP", inp.cop_hyb_e, "-"), ("하이브리드 열 COP", inp.cop_hyb_h, "-")]:
        r(g, n_, v, u, C)
    r(g, "월별 등가전부하시간", " / ".join(f"{m}월 {int(h)}h" for m, h in zip(range(1, 13), inp.heflh) if h), "h", C)
    g = "A-4 하이브리드 콘덴싱에어컨"
    for n_, v, u in [("정격 냉방능력", inp.hyb_cool_kw, "kW"), ("정격 소비전력", inp.hyb_elec_kw, "kW_e"),
                     ("정격 열 소비량", inp.hyb_heat_kw, "kW_th"), ("증발수 사용량", inp.water_lpm, "L/min")]:
        r(g, n_, v, u, C)
    r(g, "증발수 원단위", round(inp.water_lpm * 60 / inp.hyb_cool_kw, 4), "L/kWh_cool", ASM, "= 1.1×60÷11")
    r(g, "부분부하 증발수 보정", inp.water_partload_factor, "배", ASM)
    g = "A-5 연료전지(PureCell 400 NG, 1대)"
    for n_, v, u in [("발전출력", inp.fc_elec_kw, "kW_e"), ("열출력", inp.fc_heat_kw, "kW_th"),
                     ("가스 소비열량", inp.fc_gas_mj_h, "MJ/h"), ("연간 이용률", inp.fc_util, "-"),
                     ("초기 투자비", inp.fc_capex / 1e8, "억원/대")]:
        r(g, n_, v, u, C)
    r(g, "연간 등가 운전시간", round(inp.hours_year * inp.fc_util), "h", ASM, "= 8,760×95%")
    r(g, "PF", "미적용", "-", C)
    r(g, "잔존가치", None if inp.salvage is None else inp.salvage / 1e8, "억원/대", ASM)
    r(g, "철거비", None if inp.decom is None else inp.decom / 1e8, "억원/대", ASM)
    r(g, "O&M·LTSA", inp.oem_value, inp.oem_unit, ASM)
    r(g, "스택 교체주기", inp.stack_interval, "년", ASM)
    r(g, "스택 교체비", None if inp.stack_cost is None else inp.stack_cost / 1e8, "억원/대", ASM)
    r(g, "보조동력", inp.aux_kw, "kW/대", ASM)
    g = "A-6 도시가스"
    r(g, "연료전지용 도시가스 요금", inp.gas_price, "원/MJ", C)
    r(g, "부가가치세 처리", inp.gas_vat_mode, "-", C if inp.gas_vat_mode != GAS_VAT_UNKNOWN else CHK)
    r(g, "가스가격 상승률", None if inp.gas_escalation is None else inp.gas_escalation * 100, "%/년", ASM)
    g = "A-7 전력 매전"
    r(g, "220원/kWh 해석", inp.elec_mode, "-", C if inp.elec_mode_confirmed else CHK)
    r(g, "예비 검토단가", inp.elec_price_220, "원/kWh", REF)
    r(g, "일반 매전단가(HPS 제외)", inp.elec_price_base, "원/kWh", ASM)
    r(g, "HPS 목표 IRR", inp.target_irr * 100, "%", C)
    r(g, "전력가격 상승률", None if inp.elec_escalation is None else inp.elec_escalation * 100, "%/년", ASM)
    g = "A-8 열 판매"
    r(g, "FC 매열단가 비율 (지역난방 열요금 대비)", inp.fc_heat_price_ratio * 100, "%", C)
    r(g, "매열수익 인정 계절", ", ".join(inp.heat_sale_seasons), "-", C, "기본: 동절기 난방·급탕만")
    sale_idx = [i for i in range(12) if inp.season_map[i] in inp.heat_sale_seasons]
    if sale_idx and all(inp.heat_price_mwh(i) is not None for i in sale_idx):
        pv = {round(inp.district_heat_price[i], 4) for i in sale_idx}
        heat_val = (f"{pv.pop():,.2f} (매열 인정 계절 {len(sale_idx)}개월 동일)" if len(pv) == 1
                    else "매열 인정 계절 월별 입력됨")
    else:
        heat_val = None
    r(g, "지역난방 월별 열요금 (한국지역난방공사 동절기 주택용)", heat_val, inp.heat_price_unit, REF if heat_val else ASM,
      "2024.7.1 적용 요금표, 2026년 유지 안내: 115.59원/Mcal = 99.41원/kWh")
    r(g, "열가격 상승률", None if inp.heat_escalation is None else inp.heat_escalation * 100, "%/년", ASM)
    r(g, "열배관 손실률", None if inp.pipe_loss is None else inp.pipe_loss * 100, "%", ASM)
    g = "A-9 고객 요금"
    p, note = inp.elec_price_eff()
    r(g, "전기 실효단가", p, "원/kWh", REF, note)
    p, note = inp.water_price_eff()
    r(g, "수도 총단가", p, "원/㎥", REF, note)
    g = "E 경제성"
    r(g, "기준 할인율", None if inp.discount_rate is None else inp.discount_rate * 100, "%", ASM)
    r(g, "물가상승률", None if inp.inflation is None else inp.inflation * 100, "%/년", ASM)
    r(g, "보험료·제세공과금", inp.insurance, "원/년/대", ASM)
    r(g, "기타 운영비", inp.other_opex, "원/년", ASM)
    r(g, "정부보조금", inp.subsidy, "원", ASM)
    r(g, "세액공제", inp.tax_credit, "원", ASM)
    r(g, "성능저하 반영 / 연간 발전량 감소율", ("반영 " + format(inp.degradation, ".3f")) if inp.degradation_on and inp.degradation is not None else ("반영 안 함" if not inp.degradation_on else None), "-", ASM)
    df = pd.DataFrame(rows)
    df["입력값"] = df["입력값"].map(lambda v: f"{v:,.4g}" if isinstance(v, float) and abs(v) < 1e4 else (f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)))
    return df
