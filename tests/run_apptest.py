"""Streamlit AppTest로 전체 화면을 헤드리스 실행해 예외 여부를 확인한다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest

at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
print("exceptions:", [e.value for e in at.exception])
print("errors:", [e.value for e in at.error])
print("warnings:", len(at.warning), "tabs:", len(at.tabs), "dataframes:", len(at.dataframe))
