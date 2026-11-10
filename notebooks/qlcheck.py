"""독립 검증(4단계)에 쓰는 작은 도구 모음. 완성본 노트북에서 import 해서 쓴다.

검증 표는 항목 | 기준 | 실제 값 | 통과 여부 네 칸으로 보여 준다.
기준을 먼저 적고, 실제 계산 값을 그대로 적는다. 통과 여부는 기준에서 기계적으로 정한다.
"""
from __future__ import annotations

import math

try:
    from IPython.display import Markdown, display
except Exception:  # 노트북 밖(테스트)에서도 쓸 수 있게
    Markdown = None
    display = print


def _fmt(v) -> str:
    if isinstance(v, float):
        if v == 0 or 1e-4 <= abs(v) < 1e7:
            return f"{v:.10g}"
        return f"{v:.3e}"
    return str(v)


class Checks:
    """검증 항목을 모아 표로 보여 준다."""

    def __init__(self, title: str):
        self.title = title
        self.rows: list[tuple[str, str, str, bool]] = []

    def add(self, item: str, criterion: str, value, passed: bool) -> bool:
        self.rows.append((item, criterion, _fmt(value), bool(passed)))
        return bool(passed)

    def close(self, item: str, actual: float, expected: float, tol: float, rel: bool = False) -> bool:
        """|실제 - 기대| <= tol (rel=True 이면 상대오차)."""
        err = abs(actual - expected)
        if rel:
            err = err / abs(expected) if expected != 0 else err
        crit = f"{'상대' if rel else '절대'}오차 <= {tol:g} (기대 {_fmt(expected)})"
        return self.add(item, crit, f"{_fmt(actual)} (오차 {err:.2e})", err <= tol)

    def true(self, item: str, criterion: str, cond: bool, value="") -> bool:
        return self.add(item, criterion, value if value != "" else cond, cond)

    @property
    def all_passed(self) -> bool:
        return all(r[3] for r in self.rows)

    def table(self) -> str:
        lines = [f"**{self.title}**", "", "| 항목 | 기준 | 실제 값 | 통과 여부 |", "|---|---|---|---|"]
        for item, crit, val, ok in self.rows:
            lines.append(f"| {item} | {crit} | {val} | {'통과' if ok else '**실패**'} |")
        n_ok = sum(r[3] for r in self.rows)
        lines += ["", f"통과 {n_ok} / {len(self.rows)}"]
        return "\n".join(lines)

    def show(self):
        if Markdown is not None:
            display(Markdown(self.table()))
        else:
            print(self.table())
        return self


# ---------------------------------------------------------------- 커브

def curve_reprice(checks: Checks, curve, helpers, labels=None, tol: float = 1e-10) -> float:
    """커브를 만든 입력 상품을 그 커브로 다시 계산했을 때 시세와 같은지 (impliedQuote vs quote).

    모든 차이를 '소수' 단위로 맞춘다: 금리는 그대로(0.01 = 1%), 금리선물 가격(100 − 금리%)과
    채권 가격(액면 100당)은 100으로 나눈다(선물 가격 1e-8 = 금리 1e-10, 채권 가격 1e-8 = 액면의 1e-10).
    """
    import QuantLib as ql
    worst = 0.0
    n_fut = n_bond = 0
    for h in helpers:
        diff = abs(h.impliedQuote() - h.quote().value())
        if isinstance(h, ql.FuturesRateHelper):
            diff /= 100.0
            n_fut += 1
        elif isinstance(h, ql.BondHelper):
            diff /= 100.0
            n_bond += 1
        worst = max(worst, diff)
    parts = []
    if n_fut:
        parts.append(f"선물 {n_fut}개는 가격 차이 ÷ 100 = 금리 단위")
    if n_bond:
        parts.append(f"채권 {n_bond}개는 가격 차이 ÷ 100 = 액면 1당")
    note = f" ({'; '.join(parts)})" if parts else ""
    checks.add(f"입력 상품 {len(helpers)}개 재계산{note}", f"max |재계산 - 시세| <= {tol:g}", f"{worst:.2e}", worst <= tol)
    return worst


def discount_at_reference(checks: Checks, curve, name: str = "커브") -> float:
    d = curve.discount(curve.referenceDate())
    checks.close(f"{name}: 기준일 할인계수", d, 1.0, 1e-15)
    return d


def overnight_forward_jumps(curve, start, n_days: int, calendar, day_counter, compounding):
    """기준일부터 n_days 동안 하루짜리 선도금리와 하루 사이 변화량 목록."""
    import QuantLib as ql
    out = []
    d = start
    prev = None
    for _ in range(n_days):
        d2 = calendar.advance(d, 1, ql.Days)
        f = curve.forwardRate(d, d2, day_counter, compounding).rate()
        out.append((d, f, None if prev is None else f - prev))
        prev = f
        d = d2
    return out


def max_forward_jump(checks: Checks, curve, start, n_days, calendar, day_counter, compounding,
                     limit_bp: float, exclude=(), name: str = "커브"):
    """하루 사이 O/N 선도금리 변화가 limit_bp 이하인지. exclude 에 든 날짜(연말 등)는 따로 표시."""
    rows = overnight_forward_jumps(curve, start, n_days, calendar, day_counter, compounding)
    exc = set(exclude)
    jumps = [(d, abs(j) * 1e4) for d, _, j in rows if j is not None and d not in exc]
    dmax, jmax = max(jumps, key=lambda x: x[1])
    checks.add(f"{name}: 하루 사이 O/N 선도금리 최대 변화 (제외 {len(exc)}일)", f"<= {limit_bp:g}bp",
               f"{jmax:.3f}bp ({dmax})", jmax <= limit_bp)
    return jmax


# ---------------------------------------------------------------- 채권

def bond_price_yield_roundtrip(checks: Checks, bond, clean_price: float, dc, comp, freq, tol: float = 1e-8):
    import QuantLib as ql
    bp = ql.BondPrice(clean_price, ql.BondPrice.Clean)
    y = ql.BondFunctions.bondYield(bond, bp, dc, comp, freq)
    p2 = ql.BondFunctions.cleanPrice(bond, y, dc, comp, freq)
    checks.close("가격 → 수익률 → 가격", p2, clean_price, tol)
    return y


def duration_formula_vs_bump(checks: Checks, bond, yld: float, dc, comp, freq, dy: float = 1e-5,
                             tol_rel: float = 1e-4):
    """수식 수정듀레이션 vs 수익률을 ±dy 움직여 구한 -(1/P) dP/dy."""
    import QuantLib as ql
    rate = ql.InterestRate(yld, dc, comp, freq)
    d_formula = ql.BondFunctions.duration(bond, rate, ql.Duration.Modified)
    p0 = bond.dirtyPrice(yld, dc, comp, freq)
    pp = bond.dirtyPrice(yld + dy, dc, comp, freq)
    pm = bond.dirtyPrice(yld - dy, dc, comp, freq)
    d_bump = -(pp - pm) / (2 * dy) / p0
    checks.close("수정듀레이션: 수식 vs bump", d_formula, d_bump, tol_rel, rel=True)
    return d_formula, d_bump


# ---------------------------------------------------------------- 옵션

def put_call_parity(checks: Checks, call: float, put: float, spot: float, strike: float,
                    df_r: float, df_q: float, tol: float = 1e-10, name: str = "풋-콜 패리티"):
    """C - P = S*Dq - K*Dr"""
    lhs = call - put
    rhs = spot * df_q - strike * df_r
    checks.close(f"{name}: C - P = S·Dq - K·Dr", lhs, rhs, tol)
    return lhs - rhs


def bump(option, quote, h: float) -> float:
    """quote 값을 ±h 움직여 중앙차분 기울기를 구하고 원래 값으로 되돌린다."""
    x0 = quote.value()
    quote.setValue(x0 + h)
    up = option.NPV()
    quote.setValue(x0 - h)
    dn = option.NPV()
    quote.setValue(x0)
    return (up - dn) / (2 * h)


def bump2(option, quote, h: float) -> float:
    """2차 중앙차분 (감마)."""
    x0 = quote.value()
    p0 = option.NPV()
    quote.setValue(x0 + h)
    up = option.NPV()
    quote.setValue(x0 - h)
    dn = option.NPV()
    quote.setValue(x0)
    return (up - 2 * p0 + dn) / (h * h)


# ---------------------------------------------------------------- 몬테카를로

def within_std_errors(checks: Checks, item: str, estimate: float, target: float, stderr: float, k: float = 3.0):
    err = abs(estimate - target)
    ok = err <= k * stderr
    checks.add(item, f"|MC - 기준| <= {k:g} × 표준오차 (기준 {_fmt(target)})",
               f"{_fmt(estimate)} (차이 {err:.2e}, 표준오차 {stderr:.2e})", ok)
    return ok


def isclose(a, b, tol):
    return math.isclose(a, b, rel_tol=0, abs_tol=tol)
