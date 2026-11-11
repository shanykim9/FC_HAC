"""Excel 결과 다운로드. 시트별 DataFrame + 계산식 시트를 하나의 xlsx로 생성."""
from __future__ import annotations

import io
from typing import Dict, List

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def _sheet_name(n: str) -> str:
    for ch in '[]:*?/\\':
        n = n.replace(ch, "")
    return n[:31]


def build_excel(sheets: Dict[str, pd.DataFrame], formulas: List[str], notes: List[str]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        pd.DataFrame({"안내": notes}).to_excel(xw, sheet_name="00_안내", index=False)
        for name, df in sheets.items():
            if df is None:
                continue
            df.to_excel(xw, sheet_name=_sheet_name(name), index=False)
        pd.DataFrame({"계산식 및 단위 변환": formulas}).to_excel(xw, sheet_name="계산식", index=False)
        head_fill = PatternFill("solid", fgColor="1F4E78")
        for ws in xw.book.worksheets:
            for c in ws[1]:
                c.font = Font(bold=True, color="FFFFFF")
                c.fill = head_fill
                c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            ws.freeze_panes = "A2"
            for i, col in enumerate(ws.columns, 1):
                mx = max((len(str(c.value)) if c.value is not None else 0) for c in list(col)[:60])
                ws.column_dimensions[get_column_letter(i)].width = min(max(10, mx * 1.6), 70)
            for row in ws.iter_rows(min_row=2):
                for c in row:
                    if isinstance(c.value, float):
                        c.number_format = "#,##0.000" if abs(c.value) < 1000 else "#,##0.0"
    return buf.getvalue()
