"""검증 도구를 결과를 이미 아는 예제로 먼저 확인한다."""
import math
import sys
from pathlib import Path

import QuantLib as ql

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "notebooks"))
import qlcheck  # noqa: E402


def test_checks_table_and_close():
    c = qlcheck.Checks("예제")
    # 5% 연복리 2년 복리계수 = 1.05^2 = 1.1025
    r = ql.InterestRate(0.05, ql.ActualActual(ql.ActualActual.ISDA), ql.Compounded, ql.Annual)
    assert c.close("복리계수", r.compoundFactor(2.0), 1.1025, 1e-14)
    assert not c.close("틀린 기대값", 1.0, 2.0, 1e-3)
    t = c.table()
    assert "통과 1 / 2" in t and "**실패**" in t
    assert not c.all_passed


def test_put_call_parity_on_black_scholes():
    today = ql.Date(7, 3, 2014)
    ql.Settings.instance().evaluationDate = today
    u = ql.SimpleQuote(100.0)
    rts = ql.FlatForward(today, 0.03, ql.Actual365Fixed())
    qts = ql.FlatForward(today, 0.01, ql.Actual365Fixed())
    vol = ql.BlackConstantVol(today, ql.TARGET(), 0.2, ql.Actual365Fixed())
    proc = ql.BlackScholesMertonProcess(ql.QuoteHandle(u), ql.YieldTermStructureHandle(qts),
                                        ql.YieldTermStructureHandle(rts), ql.BlackVolTermStructureHandle(vol))
    ex = ql.EuropeanExercise(ql.Date(7, 3, 2015))
    eng = ql.AnalyticEuropeanEngine(proc)
    call = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Call, 100.0), ex)
    put = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Put, 100.0), ex)
    call.setPricingEngine(eng)
    put.setPricingEngine(eng)
    c = qlcheck.Checks("패리티")
    gap = qlcheck.put_call_parity(c, call.NPV(), put.NPV(), 100.0, 100.0,
                                  rts.discount(ex.lastDate()), qts.discount(ex.lastDate()), 1e-10)
    assert abs(gap) < 1e-10 and c.all_passed
    # bump 델타와 수식 델타
    assert math.isclose(qlcheck.bump(call, u, 0.01), call.delta(), abs_tol=1e-6)
    assert math.isclose(qlcheck.bump2(call, u, 0.01), call.gamma(), abs_tol=1e-5)


def test_bond_checks():
    today = ql.Date(15, 1, 2015)
    ql.Settings.instance().evaluationDate = today
    sch = ql.Schedule(today, ql.Date(15, 1, 2025), ql.Period(ql.Semiannual), ql.NullCalendar(),
                      ql.Unadjusted, ql.Unadjusted, ql.DateGeneration.Backward, False)
    dc = ql.Thirty360(ql.Thirty360.BondBasis)
    bond = ql.FixedRateBond(0, 100.0, sch, [0.05], dc)
    c = qlcheck.Checks("채권")
    # 쿠폰 = 수익률이면 액면가 근처: 왕복은 정확해야 한다
    y = qlcheck.bond_price_yield_roundtrip(c, bond, 100.0, dc, ql.Compounded, ql.Semiannual)
    assert abs(y - 0.05) < 1e-8
    d_f, d_b = qlcheck.duration_formula_vs_bump(c, bond, 0.05, dc, ql.Compounded, ql.Semiannual)
    assert c.all_passed and 7 < d_f < 8


def test_within_std_errors():
    c = qlcheck.Checks("MC")
    assert qlcheck.within_std_errors(c, "평균", 1.02, 1.0, 0.01)
    assert not qlcheck.within_std_errors(c, "평균", 1.05, 1.0, 0.01)
