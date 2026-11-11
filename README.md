# 연료전지 + 하이브리드 콘덴싱에어컨 사업성 시뮬레이터

Windows 11 / Python 3.12 / Streamlit. 모든 입력값은 UI에서 수정 가능, 결과는 Excel로 다운로드.

## 실행 (Windows)
`run.bat` 더블클릭 (venv 생성 → 패키지 설치 → 앱 실행), 또는
```
py -3.12 -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```
테스트: `python -m pytest -q tests` · 화면 헤드리스 점검: `python tests/run_apptest.py`

## 구조 (계산 로직 / UI 분리)
| 경로 | 역할 |
|---|---|
| `sim/inputs.py` | 전체 입력 데이터클래스. 값이 주어진 항목만 기본값, 추가입력 필요 항목은 `None` |
| `sim/energy_balance.py`, `cooling.py` | 열수요 환산, 냉방, 월별 에너지수지 |
| `sim/fuelcell.py`, `economics.py` | 가스비·매전·매열·운영비, 현금흐름, NPV/IRR, HPS 역산, 회수기간, 민감도 |
| `sim/efficiency.py`, `customer.py`, `storage.py` | 종합효율, 고객편익, 축열조 |
| `sim/scenarios.py`, `summary.py`, `validation.py`, `excel_export.py` | 대수 비교·추천, 경영진 요약, 기준값 검증, Excel |
| `ui/` , `app.py` | Streamlit 화면 (입력폼, A~H 섹션, 그래프 10종) |

## 핵심 원칙 구현
- 미입력 값을 임의 생성하지 않음. 빈 칸 = 추가입력 필요, 0 입력 = 0원 확정.
- 미입력 처리 모드: **참고용 제외계산**(제외 항목을 화면에 명시) / **엄격 보류**(경제성 계산 보류).
- 기준 할인율은 4.0~10.0%(0.5% 단위) 콤보박스에서 선택(기본 7%) → NPV·할인회수기간 산정. 3/5/7/10% NPV 민감도는 비교용으로 함께 표시.
- HPS 목표 IRR은 5~15%(1% 단위) 콤보박스에서 선택(기본 10%) → 해당 IRR이 되도록 필요 HPS를 이분법으로 역산(정액·원/kWh 방식).
- 220원/kWh는 "일반 매전단가" / "HPS 포함" 중 선택 → HPS 중복계상 방지.
- 하절기 냉방열(무상)·봄가을 잉여열은 매열수익 0원, 사업자 수익과 고객편익은 합산하지 않음.
- 기존 검토값(2,704MWh, 7.92억 등 14개) 자동 대조: 검증·Excel 탭.
