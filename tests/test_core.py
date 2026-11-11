import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from sim.inputs import Inputs, ELEC_S2
from sim.economics import run_economics, irr, npv
from sim.validation import validate
from sim.energy_balance import energy_balance
from sim.efficiency import efficiency_table
from sim.storage import StorageInputs, compute, empty_hourly


def full():
    i = Inputs()
    i.discount_rate = 0.05; i.oem_value = 1.0e8; i.stack_interval = 10; i.stack_cost = 3e8
    i.aux_kw = 5.0; i.aux_price = 150; i.insurance = 2e7; i.other_opex = 1e7
    i.gas_escalation = 0.02; i.elec_escalation = 0.01; i.heat_escalation = 0.01; i.inflation = 0.02
    i.subsidy = 0.0; i.salvage = 0.0; i.decom = 0.0; i.pipe_loss = 0.05
    i.district_heat_price = [100.0] * 12
    i.elec_mode_confirmed = True; i.persons_ref_confirmed = True
    return i


def test_reference_values():
    v = validate(Inputs())
    assert (v["판정"] == "일치").all(), v


def test_hps_irr_exact():
    i = full()
    for n in (1, 2, 3):
        r = run_economics(i, n)
        assert r["status"] == "ok"
        assert abs(r["hps"]["irr_after"] - i.target_irr) < 1e-8
        assert abs(r["hps"]["irr_after_kwh"] - i.target_irr) < 1e-8


def test_heat_balance_conservation():
    i = Inputs()
    b = energy_balance(i, 2)
    assert np.allclose(b["FC 발생열"], b["실제 사용열(공급열)"] + b["잉여열"] + b["배관손실열"])
    assert np.allclose(b["총 열수요"], b["실제 사용열(공급열)"] + b["부족열"])
    e = efficiency_table(i, b)
    assert abs(e.iloc[0]["전기효율"] - 400 * 3.6 / 3798.2) < 1e-9


def test_strict_hold_and_unrecovered():
    i = Inputs(); i.strict_hold = True
    assert run_economics(i, 2)["status"] == "hold"
    j = full(); r = run_economics(j, 2)
    assert "미회수" in r["m_pre"]["payback_text"] or r["m_pre"]["payback"] is not None


def test_s2_requires_base():
    i = full(); i.elec_mode = ELEC_S2
    r = run_economics(i, 2)
    assert r["cf_pre"] is None
    i.elec_price_base = 180.0
    r = run_economics(i, 2)
    assert r["hps"]["H"] > 0 and "m_bundled" in r


def test_storage_unavailable_without_data():
    out = compute(StorageInputs(hourly=empty_hourly()))
    assert not out["ok"] and "추가입력" in out["message"]


def test_irr_basic():
    assert abs(irr([-100, 110]) - 0.10) < 1e-9
    assert irr([-100, -10]) is None
