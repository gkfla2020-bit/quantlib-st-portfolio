"""매일 시장노트 도우미.

공식 무료 출처(한국은행 ECOS, 미국 재무부, 뉴욕연준, 한국거래소)에서 최신 값을 받아
숫자 표와 노트 틀을 만든다. 해석 문장은 사람이 직접 쓴다.

장별 노트북이 쓰는 data/*.json 은 2026-11-09 기준으로 고정해 두었으므로(결과 재현),
여기서는 'note_' 로 시작하는 별도 파일에만 저장한다.
"""
from __future__ import annotations

import csv
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import fetch_data as fd  # noqa: E402

DATA = ROOT / "data"
KST = timezone(timedelta(hours=9))

ECOS_ITEMS = [  # (파일 이름, 통계표, 항목, 표에 쓸 이름, 단위)
    ("note_ecos_base_rate", "722Y001", "0101000", "한국은행 기준금리", "%"),
    ("note_ecos_kofr", "817Y002", "010901000", "KOFR", "%"),
    ("note_ecos_cd91", "817Y002", "010502000", "CD 91일", "%"),
    ("note_ecos_ktb3y", "817Y002", "010200000", "국고채 3년", "%"),
    ("note_ecos_ktb10y", "817Y002", "010210000", "국고채 10년", "%"),
    ("note_ecos_usdkrw", "731Y001", "0000001", "원/달러(매매기준율)", "원"),
]
UST_URL = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
           "{y}/all?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv")
SOFR_URL = "https://markets.newyorkfed.org/api/rates/secured/sofr/last/10.json"


def refresh(days: int = 21) -> list[tuple[str, str]]:
    """모든 출처를 다시 받는다. 돌려주는 값: [(이름, 'ok' 또는 오류 문장)]"""
    out = []
    jobs = [(n, (lambda s=s, i=i, n=n, t=t: fd.ecos_recent(s, i, n, f"{t} 최근 영업일(시장노트)", days)))
            for n, s, i, t, _ in ECOS_ITEMS]
    year = datetime.now(KST).year
    jobs += [("note_ust_par", lambda: fd._save("note_ust_par", "csv", fd._get(UST_URL.format(y=year)), UST_URL.format(y=year),
                                               "U.S. Department of the Treasury", f"{year}년 par yield(시장노트)")),
             ("note_nyfed_sofr", lambda: fd._save("note_nyfed_sofr", "json", fd._get(SOFR_URL), SOFR_URL,
                                                  "Federal Reserve Bank of New York", "SOFR 최근 10영업일(시장노트)")),
             ("note_krx_idx_representative", lambda: fd.krx_index_snapshot("01", "02", "note_krx_idx_representative",
                                                                           "KRX 대표지수 현재가(시장노트)")),
             ("note_krx_idx_option", lambda: fd.krx_index_snapshot("02", "02", "note_krx_idx_option",
                                                                   "KRX 옵션지수 현재가(시장노트)"))]
    for name, job in jobs:
        try:
            job()
            out.append((name, "ok"))
        except Exception as e:  # 한 출처가 실패해도 나머지는 받는다
            out.append((name, f"{type(e).__name__}: {e}"))
    return out


def _ecos_series(name: str) -> list[tuple[str, float]]:
    rows = json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))["StatisticSearch"]["row"]
    return sorted((r["TIME"], float(r["DATA_VALUE"])) for r in rows)


def _change(series: list[tuple[str, float]], lag: int):
    if len(series) <= lag:
        return None
    return series[-1][1] - series[-1 - lag][1]


def _ust_series(tenor_col: str) -> list[tuple[str, float]]:
    rows = list(csv.DictReader(io.StringIO((DATA / "note_ust_par.csv").read_text())))
    return sorted((datetime.strptime(r["Date"], "%m/%d/%Y").strftime("%Y%m%d"), float(r[tenor_col]))
                  for r in rows if r.get(tenor_col))


def _sofr_series() -> list[tuple[str, float]]:
    rows = json.loads((DATA / "note_nyfed_sofr.json").read_text())["refRates"]
    return sorted((r["effectiveDate"].replace("-", ""), r["percentRate"]) for r in rows)


def _krx(name: str) -> tuple[float, float, str]:
    """(현재가, 전일 대비, 조회 시각) — KRX 화면은 과거 값을 주지 않아 1주 변화는 없음"""
    for f in ("note_krx_idx_representative", "note_krx_idx_option"):
        for r in json.loads((DATA / f"{f}.json").read_text(encoding="utf-8"))["output"]:
            if r["idx_nm"] == name:
                px = float(r["prsnt_prc"].replace(",", ""))
                rate = float(r["idx_fluc_rt"])
                chg = float(r["cmpprevdd"].replace(",", "")) * (1 if rate >= 0 else -1)
                return px, chg, fd_manifest(f)["fetched_at_kst"]
    raise KeyError(name)


def fd_manifest(name: str) -> dict:
    return json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))[name]


def table() -> list[dict]:
    """시장노트 숫자 표. 금리 변화는 bp, 환율·지수 변화는 원래 단위."""
    rows = []
    for name, _, _, label, unit in ECOS_ITEMS:
        s = _ecos_series(name)
        k = 100 if unit == "%" else 1
        rows.append(dict(group="원화 금리" if unit == "%" else "환율", item=label, value=s[-1][1], unit=unit, day=s[-1][0],
                         d1=None if _change(s, 1) is None else _change(s, 1) * k,
                         d5=None if _change(s, 5) is None else _change(s, 5) * k,
                         chg_unit="bp" if unit == "%" else unit, source="한국은행 ECOS"))
    for col, label in (("2 Yr", "미국채 2년(par)"), ("10 Yr", "미국채 10년(par)")):
        s = _ust_series(col)
        rows.append(dict(group="달러 금리", item=label, value=s[-1][1], unit="%", day=s[-1][0],
                         d1=_change(s, 1) * 100, d5=_change(s, 5) * 100, chg_unit="bp", source="미국 재무부"))
    s2, s10 = _ust_series("2 Yr"), _ust_series("10 Yr")
    spread = [(d, b - a) for (d, a), (_, b) in zip(s2, s10)]
    rows.append(dict(group="달러 금리", item="미국 2s10s(10년 − 2년)", value=spread[-1][1] * 100, unit="bp", day=spread[-1][0],
                     d1=_change(spread, 1) * 100, d5=_change(spread, 5) * 100, chg_unit="bp", source="미국 재무부(계산)"))
    s = _sofr_series()
    rows.append(dict(group="달러 금리", item="SOFR", value=s[-1][1], unit="%", day=s[-1][0],
                     d1=_change(s, 1) * 100, d5=_change(s, 5) * 100, chg_unit="bp", source="뉴욕연준"))
    for label in ("코스피 200", "코스피 200 변동성지수"):
        px, chg, at = _krx(label)
        rows.append(dict(group="주식·변동성", item=label + (" (VKOSPI)" if "변동성" in label else ""), value=px, unit="pt",
                         day=at, d1=chg, d5=None, chg_unit="pt", source="한국거래소 지수 사이트"))
    return rows


def show(rows: list[dict]) -> str:
    f = lambda v, u: "—" if v is None else (f"{v:+.1f}{u}" if u == "bp" else f"{v:+,.2f}{u}")  # noqa: E731
    out = ["| 구분 | 지표 | 값 | 전일 대비 | 1주(5영업일) 대비 | 기준일·조회 시각 | 출처 |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        val = f"{r['value']:,.3f}{r['unit']}" if r["unit"] == "%" else f"{r['value']:,.2f}{r['unit']}"
        out.append(f"| {r['group']} | {r['item']} | {val} | {f(r['d1'], r['chg_unit'])} | {f(r['d5'], r['chg_unit'])} | {r['day']} | {r['source']} |")
    return "\n".join(out)


def note_template(rows: list[dict]) -> str:
    """복사해서 쓰는 노트 틀. 숫자는 자동, [ ] 칸은 직접 쓴다."""
    by = {r["item"]: r for r in rows}
    today = datetime.now(KST).strftime("%Y-%m-%d (%a)")
    k3, k10 = by["국고채 3년"], by["국고채 10년"]
    u2, u10 = by["미국채 2년(par)"], by["미국채 10년(par)"]
    fx = by["원/달러(매매기준율)"]
    return "\n".join([
        f"# 시장노트 {today}",
        "## 1. 숫자 (자동)",
        f"- 국고 3년 {k3['value']:.3f}% ({k3['d1']:+.1f}bp), 10년 {k10['value']:.3f}% ({k10['d1']:+.1f}bp), "
        f"3-10 스프레드 {(k10['value'] - k3['value']) * 100:.1f}bp",
        f"- 미국 2년 {u2['value']:.2f}% ({u2['d1']:+.1f}bp), 10년 {u10['value']:.2f}% ({u10['d1']:+.1f}bp), 2s10s {by['미국 2s10s(10년 − 2년)']['value']:.0f}bp",
        f"- 원/달러 {fx['value']:,.1f}원 ({fx['d1']:+,.1f}원), KOFR {by['KOFR']['value']:.3f}%, CD91 {by['CD 91일']['value']:.2f}%",
        f"- 코스피200 {by['코스피 200']['value']:,.2f} ({by['코스피 200']['d1']:+,.2f}), VKOSPI {by['코스피 200 변동성지수 (VKOSPI)']['value']:.2f}",
        "## 2. 무엇이 움직였나 (직접)",
        "- [ ] 가장 크게 움직인 지표와 그 이유(뉴스·지표 발표·수급) 한 줄",
        "- [ ] 국내 금리와 미국 금리가 같은 방향이었나? 아니라면 왜?",
        "## 3. 데스크 관점 (직접)",
        "- [ ] 국채선물 헤지 고객에게 할 말 한 줄(24장 DV01 관점)",
        "- [ ] ELS·옵션 쪽: VKOSPI 변화가 발행·헤지에 주는 의미 한 줄",
        "## 4. 내일 볼 것 (직접)",
        "- [ ] 발표 일정(금통위·FOMC·CPI·국채 입찰)과 예상",
    ])
