"""공식 기관에서 내려받아 data/ 에 저장한 자료를 읽는 함수 모음 (완성본 노트북 버전 2·실무 연습에서 쓴다).

자료를 내려받는 코드는 tools/fetch_data.py, 출처·조회 시각은 data/manifest.json 에 있다.
노트북은 인터넷에 다시 묻지 않고 저장된 파일만 읽으므로, 다시 실행해도 같은 숫자가 나온다.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import QuantLib as ql

DATA = Path(__file__).resolve().parents[1] / "data"


def _korean_font():
    """그래프의 한글이 깨지지 않게 시스템에 있는 한글 글꼴을 고른다(맥: AppleGothic)."""
    try:
        import matplotlib
        from matplotlib import font_manager
        names = {f.name for f in font_manager.fontManager.ttflist}
        for cand in ("AppleGothic", "Apple SD Gothic Neo", "NanumGothic", "Malgun Gothic", "Noto Sans CJK KR"):
            if cand in names:
                matplotlib.rcParams["font.family"] = cand
                matplotlib.rcParams["axes.unicode_minus"] = False
                return cand
    except Exception:
        pass
    return None


KOREAN_FONT = _korean_font()


def manifest(name: str) -> dict:
    return json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))[name]


def source_line(name: str) -> str:
    m = manifest(name)
    return f"{m['publisher']} · {m['note']} · 조회 {m['fetched_at_kst']} · {m['url']}"


# ---------------------------------------------------------------- 날짜

def qdate(s: str) -> ql.Date:
    """'20261109', '2026-11-09', '11/09/2026' -> ql.Date"""
    s = s.strip()
    if "/" in s:
        m, d, y = map(int, s.split("/"))
    elif "-" in s:
        y, m, d = map(int, s.split("-"))
    else:
        y, m, d = int(s[:4]), int(s[4:6]), int(s[6:])
    return ql.Date(d, m, y)


# ---------------------------------------------------------------- 한국

def krx_holidays() -> dict:
    """KRX 공식 휴장일 {ql.Date: 이름} (data/krx_holidays_YYYY.json 전부)"""
    out = {}
    for p in sorted(DATA.glob("krx_holidays_*.json")):
        for r in json.loads(p.read_text(encoding="utf-8"))["block1"]:
            out[qdate(r["calnd_dd"])] = r["holdy_nm"]
    return out


def krx_calendar(market=None) -> ql.Calendar:
    """QuantLib SouthKorea 달력에 KRX 공식 휴장일 중 빠진 날을 더한다 (1장에서 확인한 차이 보정).

    market=Settlement(결제·자금시장)이면 거래소만 쉬는 '연말휴장일'(12/31)은 넣지 않는다.
    근거: 2025-12-31에도 KOFR(익일물 RP 금리)가 공시됐다(data/ecos_kofr_yearend_2025.json) → 자금시장은 열렸다.
    주의: addHoliday 는 같은 종류 달력 전체(이 파이썬 세션)에 적용된다.
    """
    m = ql.SouthKorea.KRX if market is None else market
    cal = ql.SouthKorea(m)
    for d, name in krx_holidays().items():
        if m == ql.SouthKorea.Settlement and "연말휴장" in name:
            continue
        if cal.isBusinessDay(d):
            cal.addHoliday(d)
    return cal


def krx_index(name: str) -> float:
    """KRX 지수 사이트 조회값(현재가). 예: '코스피 200', '코스피 200 변동성지수'"""
    for f in ("krx_idx_representative.json", "krx_idx_option.json"):
        rows = json.loads((DATA / f).read_text(encoding="utf-8"))["output"]
        for r in rows:
            if r["idx_nm"] == name:
                return float(r["prsnt_prc"].replace(",", ""))
    raise KeyError(name)


def ecos_rows(name: str) -> list[dict]:
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))["StatisticSearch"]["row"]


def ecos_latest(name: str) -> tuple[ql.Date, float]:
    """(날짜, 소수 금리). 예: ecos_latest('ecos_kofr') -> (Date(5,11,2026), 0.03045)"""
    r = ecos_rows(name)[-1]
    return qdate(r["TIME"]), float(r["DATA_VALUE"]) / 100


KTB_TENORS = [1, 2, 3, 5, 10, 20, 30, 50]


def ktb_yields(day: str | None = None) -> tuple[ql.Date, dict]:
    """국고채 만기별 금리 {년: 소수}. day='20261109' 처럼 고르거나, 없으면 3년물의 가장 최근 날짜."""
    series = {t: ecos_rows(f"ecos_ktb{t}y") for t in KTB_TENORS}
    if day is None:
        day = series[3][-1]["TIME"]
    out = {}
    for t, rows in series.items():
        r = next(r for r in rows if r["TIME"] == day)
        out[t] = float(r["DATA_VALUE"]) / 100
    return qdate(day), out


def ktb_days() -> list[str]:
    """국고채 금리가 있는 날짜 목록(오래된 것부터)"""
    return [r["TIME"] for r in ecos_rows("ecos_ktb3y")]


# ---------------------------------------------------------------- 해외

def sofr_latest() -> tuple[ql.Date, float]:
    r = json.loads((DATA / "nyfed_sofr.json").read_text())["refRates"][0]
    return qdate(r["effectiveDate"]), r["percentRate"] / 100


def estr_latest() -> tuple[ql.Date, float]:
    rows = list(csv.DictReader(io.StringIO((DATA / "ecb_estr.csv").read_text())))
    r = rows[-1]
    return qdate(r["TIME_PERIOD"]), float(r["OBS_VALUE"]) / 100


def sonia_latest() -> tuple[ql.Date, float]:
    import datetime
    last = (DATA / "boe_sonia.csv").read_text().strip().split("\n")[-1]
    d, v = last.split(",")
    dt = datetime.datetime.strptime(d.strip(), "%d %b %Y")
    return ql.Date(dt.day, dt.month, dt.year), float(v) / 100


UST_COLS = [("1 Mo", 1 / 12), ("2 Mo", 2 / 12), ("3 Mo", 0.25), ("6 Mo", 0.5), ("1 Yr", 1), ("2 Yr", 2), ("3 Yr", 3),
            ("5 Yr", 5), ("7 Yr", 7), ("10 Yr", 10), ("20 Yr", 20), ("30 Yr", 30)]


def ust_par_yields(row: int = 0) -> tuple[ql.Date, dict]:
    """미국 재무부 par yield {년: 소수}. row=0 이 가장 최근 날짜."""
    rows = list(csv.DictReader(io.StringIO((DATA / "ust_par_curve_2026.csv").read_text())))
    r = rows[row]
    return qdate(r["Date"]), {t: float(r[c]) / 100 for c, t in UST_COLS if r.get(c)}


# ---------------------------------------------------------------- 커브

CURVE_DC = ql.Actual365Fixed()


def par_bond_curve(today: ql.Date, yields: dict, calendar: ql.Calendar, day_count: ql.DayCounter,
                   settlement_days: int = 1, freq=ql.Semiannual, min_tenor: float = 1.0, relative: bool = True,
                   curve_day_count: ql.DayCounter = CURVE_DC):
    """만기별 par yield를 '쿠폰 = 금리, 가격 = 100'인 채권으로 보고 부트스트래핑한 할인 커브.

    1년 미만 만기는 넣지 않는다(min_tenor). relative=True 면 기준일이 평가일을 따라 움직인다.
    day_count 는 채권 쿠폰의 일수 계산, curve_day_count 는 커브의 시간 축(기본 Actual/365 Fixed).
    둘을 나누는 이유: Actual/Actual(ISMA·Bond)를 이표 일정 없이 커브에 쓰면 QuantLib이 기간을
    '반올림한 개월 수 / 12'로 계산해(1.44 actualactual.cpp의 Old_ISMA_Impl) 보름 안쪽 날짜들의 시간이 같아진다.
    돌려주는 값: (curve, helpers, schedules, quotes)
    """
    day_count_curve = curve_day_count
    settle = calendar.advance(today, settlement_days, ql.Days)
    helpers, schedules, quotes = [], [], []
    for t in sorted(yields):
        if t < min_tenor:
            continue
        q = ql.SimpleQuote(100.0)
        maturity = calendar.advance(settle, int(round(t * 12)), ql.Months)
        sch = ql.Schedule(settle, maturity, ql.Period(freq), calendar, ql.Unadjusted, ql.Unadjusted,
                          ql.DateGeneration.Backward, False)
        helpers.append(ql.FixedRateBondHelper(ql.QuoteHandle(q), settlement_days, 100.0, sch, [yields[t]], day_count))
        schedules.append(sch)
        quotes.append(q)
    if relative:
        curve = ql.PiecewiseLogLinearDiscount(0, calendar, helpers, day_count_curve)
    else:
        curve = ql.PiecewiseLogLinearDiscount(today, helpers, day_count_curve)
    curve.enableExtrapolation()
    return curve, helpers, schedules, quotes
