"""공식 기관 자료를 내려받아 data/ 에 원본 그대로 저장하고, 주소·조회 시각을 data/manifest.json 에 남긴다.

노트북은 인터넷에 다시 묻지 않고 여기 저장된 파일을 읽는다(나중에 다시 실행해도 같은 숫자).

사용법: python tools/fetch_data.py <이름> [이름 ...]     (이름 목록은 SOURCES 참고)
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MANIFEST = DATA / "manifest.json"
KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (personal study; QuantLib cookbook)"}

KRX_PAGE = "https://open.krx.co.kr/contents/MKD/01/0110/01100305/MKD01100305.jsp"
ECOS = "https://ecos.bok.or.kr/api/StatisticSearch/sample/json/kr/{a}/{b}/{stat}/{cycle}/{start}/{end}/{item}"


def _get(url: str, data: bytes | None = None, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _save(name: str, ext: str, body: bytes, url: str, publisher: str, note: str, method: str = "GET",
          params: dict | None = None) -> Path:
    DATA.mkdir(exist_ok=True)
    path = DATA / f"{name}.{ext}"
    path.write_bytes(body)
    man = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    man[name] = {
        "file": path.name,
        "publisher": publisher,
        "url": url,
        "method": method,
        "params": params or {},
        "fetched_at_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST"),
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
        "note": note,
    }
    MANIFEST.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def krx_holidays(year: int) -> Path:
    """한국거래소 정보데이터시스템 '휴장일' 화면이 쓰는 조회(OTP 발급 후 조회)."""
    bld = "MKD/01/0110/01100305/mkd01100305_01"
    otp = _get("https://open.krx.co.kr/contents/COM/GenerateOTP.jspx?" +
               urllib.parse.urlencode({"bld": bld, "name": "form"}), headers={"Referer": KRX_PAGE})
    params = {"search_bas_yy": str(year), "gridTp": "KRX",
              "pagePath": "/contents/MKD/01/0110/01100305/MKD01100305.jsp"}
    body = _get("https://open.krx.co.kr/contents/OPN/99/OPN99000001.jspx",
                data=urllib.parse.urlencode({**params, "code": otp.decode()}).encode(),
                headers={"Referer": KRX_PAGE})
    return _save(f"krx_holidays_{year}", "json", body, KRX_PAGE, "한국거래소(KRX)",
                 f"{year}년 증권시장 휴장일(화면: 정보데이터시스템 > 휴장일)", "POST", params)


def nyfed_sofr(n: int = 30) -> Path:
    url = f"https://markets.newyorkfed.org/api/rates/secured/sofr/last/{n}.json"
    return _save("nyfed_sofr", "json", _get(url), url, "Federal Reserve Bank of New York",
                 f"SOFR 최근 {n}영업일")


def ecb_estr(n: int = 30) -> Path:
    url = f"https://data-api.ecb.europa.eu/service/data/EST/B.EU000A2X2A25.WT?lastNObservations={n}&format=csvdata"
    return _save("ecb_estr", "csv", _get(url), url, "European Central Bank", f"€STR 최근 {n}영업일")


def boe_sonia(days: int = 45) -> Path:
    end = datetime.now(KST).date()
    start = end - timedelta(days=days)
    f = lambda d: d.strftime("%d/%b/%Y")  # noqa: E731
    url = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes"
           f"&Datefrom={f(start)}&Dateto={f(end)}&SeriesCodes=IUDSOIA&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N")
    return _save("boe_sonia", "csv", _get(url), url, "Bank of England", "SONIA (IUDSOIA)")


def ust_par_curve(year: int) -> Path:
    url = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
           f"{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv")
    return _save(f"ust_par_curve_{year}", "csv", _get(url), url, "U.S. Department of the Treasury",
                 f"{year}년 Daily Treasury Par Yield Curve Rates")


def ecos(stat: str, item: str, start: str, end: str, name: str, note: str, cycle: str = "D") -> Path:
    """한국은행 ECOS Open API (공개 sample 키는 한 번에 10행까지라 10행씩 나눠 받아 합친다)."""
    rows, a, total = [], 1, None
    first_url = ECOS.format(a=1, b=10, stat=stat, cycle=cycle, start=start, end=end, item=item)
    while total is None or a <= total:
        url = ECOS.format(a=a, b=a + 9, stat=stat, cycle=cycle, start=start, end=end, item=item)
        j = json.loads(_get(url))
        ss = j["StatisticSearch"]
        total = int(ss["list_total_count"])
        rows += ss["row"]
        a += 10
    body = json.dumps({"StatisticSearch": {"list_total_count": total, "row": rows}}, ensure_ascii=False,
                      indent=1).encode()
    return _save(name, "json", body, first_url, "한국은행 ECOS", note + f" ({total}행, 10행씩 나눠 받음)")


def ecos_items(stat: str, name: str) -> Path:
    rows = []
    for a in range(1, 41, 10):
        url = f"https://ecos.bok.or.kr/api/StatisticItemList/sample/json/kr/{a}/{a + 9}/{stat}"
        j = json.loads(_get(url))
        rows += j.get("StatisticItemList", {}).get("row", [])
    body = json.dumps(rows, ensure_ascii=False, indent=1).encode()
    return _save(name, "json", body, f"https://ecos.bok.or.kr/api/StatisticItemList/sample/json/kr/1/10/{stat}",
                 "한국은행 ECOS", f"통계표 {stat} 항목 목록")


KRX_IDX_PAGE = "https://index.krx.co.kr/contents/MKD/03/0304/03040200/MKD03040200.jsp"


def krx_index_snapshot(up: str, mid: str, name: str, note: str) -> Path:
    """KRX 지수 사이트(index.krx.co.kr) '주가지수' 화면의 지수 목록과 현재가(prsnt_prc)."""
    bld = "/IDX/03/0304/03040100/mkd03040100"
    otp = _get("https://index.krx.co.kr/contents/COM/GenerateOTP.jspx?" +
               urllib.parse.urlencode({"bld": bld, "name": "grid"}), headers={"Referer": KRX_IDX_PAGE})
    today = datetime.now(KST).strftime("%Y%m%d")
    params = {"idx_upclss_cd": up, "idx_midclss_cd": mid, "lang": "ko", "bz_dd": today}
    body = _get("https://index.krx.co.kr/contents/IDX/99/IDX99000001.jspx",
                data=urllib.parse.urlencode({**params, "code": otp.decode()}).encode(),
                headers={"Referer": KRX_IDX_PAGE})
    return _save(name, "json", body, KRX_IDX_PAGE, "한국거래소(KRX) 지수 사이트", note, "POST", params)


def ecos_recent(stat: str, item: str, name: str, note: str, days: int = 20) -> Path:
    end = datetime.now(KST).date()
    start = end - timedelta(days=days)
    return ecos(stat, item, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), name, note)


FISCAL_AUCTIONS = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query"
AUCTION_FIELDS = ("cusip,security_type,security_term,original_security_term,auction_date,issue_date,dated_date,"
                  "maturity_date,int_rate,reopening,first_int_payment_date,int_payment_frequency,"
                  "inflation_index_security,floating_rate,high_yield")


def ust_note_auctions(name: str, mat_from: str, mat_to: str, note: str) -> Path:
    """미국 재무부 Fiscal Data 'Treasury Securities Auctions Data'에서 만기가 [mat_from, mat_to]인 Note 입찰 기록."""
    url = (f"{FISCAL_AUCTIONS}?filter=security_type:eq:Note,maturity_date:gte:{mat_from},maturity_date:lte:{mat_to}"
           f"&fields={AUCTION_FIELDS}&sort=maturity_date,issue_date&page[size]=500")
    return _save(name, "json", _get(url), url, "U.S. Department of the Treasury (Fiscal Data)", note)


def official_page(name: str, url: str, publisher: str, note: str) -> Path:
    """근거로 쓰는 공식 안내 페이지를 HTML 그대로 저장한다."""
    return _save(name, "html", _get(url), url, publisher, note)


PAGES = {
    "krx_kospi200_futures": ("https://open.krx.co.kr/contents/OPN/01/01040201/OPN01040201.jsp", "한국거래소(KRX)",
                             "주가지수상품(코스피200선물) 상품명세"),
    "krx_kospi200_options": ("https://open.krx.co.kr/contents/OPN/01/01040202/OPN01040202.jsp", "한국거래소(KRX)",
                             "코스피200옵션 상품명세"),
    "krx_ktb_futures": ("https://open.krx.co.kr/contents/OPN/01/01040501/OPN01040501.jsp", "한국거래소(KRX)",
                        "채권/금리상품(3년국채선물) 상품명세"),
    "krx_kofr_futures": ("https://open.krx.co.kr/contents/OPN/01/01040505/OPN01040505.jsp", "한국거래소(KRX)",
                         "3개월무위험지표금리선물 상품명세"),
    "moef_ntndbtKnd": ("https://ktb.moef.go.kr/ntndbtKnd.do", "기획재정부 국고채 사이트",
                       "국채종류: 국고채권 이자지급 '매6월후급'"),
    "moef_ntndbtUnityIsu": ("https://ktb.moef.go.kr/ntndbtUnityIsu.do", "기획재정부 국고채 사이트",
                            "국고채 통합발행 주기와 연간 신규발행일(예: 3년물 6월 10일·12월 10일)"),
    "moef_ntndbtFtrs": ("https://ktb.moef.go.kr/ntndbtFtrs.do", "기획재정부 국고채 사이트",
                        "국채선물: 기초자산(표면금리 5%), 결제월, 최종거래일, 현금결제"),
    "moef_distbMrktIntrcn": ("https://ktb.moef.go.kr/distbMrktIntrcn.do", "기획재정부 국고채 사이트",
                             "유통시장 소개: 장내시장 결제시점 익일 결제"),
    "fca_libor_transition": ("https://www.fca.org.uk/markets/libor-transition", "영국 금융감독청(FCA)",
                             "LIBOR 전환 안내: 'The interest rate benchmark LIBOR has permanently ceased.'"),
    "fca_libor_end_announcements": ("https://www.fca.org.uk/news/press-releases/announcements-end-libor", "영국 금융감독청(FCA)",
                                    "2021-03-05 LIBOR 종료 날짜 발표(미국 달러 대부분 만기 2023-06-30 이후 종료)"),
    "fss_hscei_els_20240311": ("https://www.fss.or.kr/fss/bbs/B0000188/view.do?nttId=134558&menuNo=200218", "금융감독원",
                               "홍콩 H지수 ELS 검사결과(잠정) 및 분쟁조정기준(안)"),
    "fss_hscei_els_sanction": ("https://www.fss.or.kr/fss/bbs/B0000188/view.do?nttId=249736&menuNo=200218", "금융감독원",
                               "홍콩 H지수 ELS 관련 은행, 증권사 검사 결과 조치"),
}


SOURCES = {
    **{k: (lambda k=k: official_page(k, *PAGES[k])) for k in PAGES},
    "krx_idx_representative": lambda: krx_index_snapshot("01", "02", "krx_idx_representative",
                                                         "KRX KOSPI 시리즈 목록과 현재가(코스피 200 포함)"),
    "krx_idx_option": lambda: krx_index_snapshot("02", "02", "krx_idx_option",
                                                 "KRX 옵션지수 목록과 현재가(코스피 200 변동성지수=VKOSPI 포함)"),
    "ecos_kofr": lambda: ecos_recent("817Y002", "010901000", "ecos_kofr", "KOFR(공시RFR) 최근 영업일"),
    "ecos_cd91": lambda: ecos_recent("817Y002", "010502000", "ecos_cd91", "CD(91일) 최근 영업일"),
    "ecos_ktb3y": lambda: ecos_recent("817Y002", "010200000", "ecos_ktb3y", "국고채(3년) 최근 영업일"),
    **{f"ecos_ktb{t}": (lambda t=t, c=c: ecos_recent("817Y002", c, f"ecos_ktb{t}", f"국고채({t}) 최근 영업일"))
       for t, c in [("1y", "010190000"), ("2y", "010195000"), ("5y", "010200001"), ("20y", "010220000"),
                    ("30y", "010230000"), ("50y", "010240000")]},
    "ecos_ktb10y": lambda: ecos_recent("817Y002", "010210000", "ecos_ktb10y", "국고채(10년) 최근 영업일"),
    "ecos_corp_aa3y": lambda: ecos_recent("817Y002", "010300000", "ecos_corp_aa3y", "회사채(3년, AA-) 최근 영업일"),
    "ecos_corp_bbb3y": lambda: ecos_recent("817Y002", "010320000", "ecos_corp_bbb3y", "회사채(3년, BBB-) 최근 영업일"),
    "krx_holidays_2026": lambda: krx_holidays(2026),
    "krx_holidays_2027": lambda: krx_holidays(2027),
    "nyfed_sofr": nyfed_sofr,
    "ecb_estr": ecb_estr,
    "boe_sonia": boe_sonia,
    "boe_bank_rate_2026h2": lambda: _save("boe_bank_rate_2026h2", "csv", _get(
        "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Jul/2026&Dateto=09/Nov/2026"
        "&SeriesCodes=IUDBEDR&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N"),
        "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Jul/2026&Dateto=09/Nov/2026"
        "&SeriesCodes=IUDBEDR&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N", "Bank of England", "Bank Rate (IUDBEDR) 일별 2026-07-01 ~ 2026-11-09"),
    "boe_sonia_2026h2": lambda: _save("boe_sonia_2026h2", "csv", _get(
        "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Jul/2026&Dateto=09/Nov/2026"
        "&SeriesCodes=IUDSOIA&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N"),
        "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Jul/2026&Dateto=09/Nov/2026"
        "&SeriesCodes=IUDSOIA&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N", "Bank of England", "SONIA (IUDSOIA) 2026-07-01 ~ 2026-11-09"),
    "ust_par_curve_2026": lambda: ust_par_curve(2026),
    "garp_frm_study_guide_2026": lambda: _save(
        "garp_frm_study_guide_2026", "pdf",
        _get("https://www.garp.org/hubfs/GARP%20Design/frm/pdf/study-materials/2026/frm-study-guide-26.pdf"),
        "https://www.garp.org/hubfs/GARP%20Design/frm/pdf/study-materials/2026/frm-study-guide-26.pdf", "GARP",
        "2026 FRM Study Guide: Part I 4개 영역(비중 20/20/30/30%)과 장 목록"),
    "ust_auctions_ty2015z": lambda: ust_note_auctions(
        "ust_auctions_ty2015z", "2022-06-01", "2025-12-01",
        "만기 2022-06-01 ~ 2025-12-01 Note 입찰 기록(책 24장 TYZ5 바스켓 대조용: 2015-12-01 기준 잔존 6.5~10년)"),
    "ust_auctions_ty2026z": lambda: ust_note_auctions(
        "ust_auctions_ty2026z", "2033-06-01", "2034-12-01",
        "만기 2033-06-01 ~ 2034-12-01 Note 입찰 기록(TYZ6 바스켓: 2026-12-01 기준 잔존 6년 6개월 ~ 8년)"),
    "ecos_817Y002_items": lambda: ecos_items("817Y002", "ecos_817Y002_items"),
    "ecos_base_rate_2025_2026": lambda: ecos("722Y001", "0101000", "20250101", "20261109", "ecos_base_rate_2025_2026",
                                             "한국은행 기준금리 일별 2025-01-01 ~ 2026-11-09"),
    "ecos_kofr_2025_2026": lambda: ecos("817Y002", "010901000", "20250101", "20261109", "ecos_kofr_2025_2026",
                                        "KOFR(공시RFR) 일별 2025-01-01 ~ 2026-11-09"),
    **{f"ecos_ktb{t}_hist": (lambda t=t, c=c: ecos("817Y002", c, "20251101", "20261109", f"ecos_ktb{t}_hist",
                                                   f"국고채({t}) 일별 2025-11-01 ~ 2026-11-09 (실현 변동성 계산용)"))
       for t, c in [("3y", "010200000"), ("10y", "010210000")]},
    "bok_mpc_2026": lambda: official_page(
        "bok_mpc_2026", "https://www.bok.or.kr/portal/singl/crncyPolicyDrcMtg/listYear.do?mtgSe=A&menuNo=200755",
        "한국은행", "통화정책방향 결정회의 일정 2026년(1/15, 2/26, 4/10, 5/28, 7/16, 8/27, 10/22, 11/26). 2027년 화면은 일정 없음(2026-11-09 조회)"),
}


def main() -> None:
    for name in sys.argv[1:]:
        p = SOURCES[name]()
        print(f"{name}: {p.relative_to(ROOT)} ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
