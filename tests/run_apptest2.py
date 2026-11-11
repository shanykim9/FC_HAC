import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest

def run(setup, label):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
    setup(at)
    at.run()
    print(label, "| exceptions:", [e.value for e in at.exception], "| errors:", [e.value for e in at.error], "| warnings:", len(at.warning))
    return at

def filled(at):
    at.selectbox(key="disc").set_value(5.0)
    for k, v in dict(oem=1e8, sint=10.0, scost=3e8, auxkw=5.0, auxp=150.0, ins=2e7, oth=1e7, gesc=2.0, eesc=1.0,
                     hesc=1.0, infl=2.0, sub=0.0, salv=0.0, decom=0.0, ploss=5.0, wpl=1.2, ebase=180.0).items():
        at.number_input(key=k).set_value(v)
    at.checkbox(key="emode_ok").set_value(True)
    at.checkbox(key="pref_ok").set_value(True)

def s2(at):
    filled(at)
    at.radio(key="emode").set_value("220원/kWh = 매전단가+HPS 포함 (HPS 별도 가산 없음)")

def strict(at):
    at.radio(key="strict").set_value("엄격 보류")

def manual(at):
    filled(at)
    at.radio(key="n_mode").set_value("수동 지정")
    at.number_input(key="n_manual").set_value(3)
    at.number_input(key="n_max").set_value(12)

run(lambda a: None, "default")
run(filled, "filled")
run(s2, "S2")
run(strict, "strict")
run(manual, "manual N=3")

def deg(at):
    filled(at)
    at.checkbox(key="deg_on").set_value(True).run()
    at.number_input(key="deg").set_value(0.5)
run(deg, "degradation on")
