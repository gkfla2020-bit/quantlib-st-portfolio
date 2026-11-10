#%% md
# 매일 시장노트 (S&T 준비용)

**목적**: 매일 같은 숫자를 같은 방식으로 적어 두면, 몇 주 뒤에는 '오늘 무엇이 평소와 다른지'가 바로 보입니다. 면접에서 "요즘 시장을 어떻게 보세요?"에 숫자로 답하는 연습이기도 합니다.

**쓰는 법**
1. 아침(국내 장 시작 뒤)에 이 노트북을 위에서부터 실행합니다. 공식 무료 출처에서 최신 값을 받습니다.
2. 2절 표와 3절 노트 틀을 복사해 개인 노트에 붙이고, `[ ]` 칸만 직접 씁니다.
3. 금요일에는 4절의 주간 정리 질문에 답합니다.

| 지표 | 출처 | 비고 |
|---|---|---|
| 기준금리, KOFR, CD 91일, 국고채 3·10년, 원/달러 | 한국은행 ECOS Open API | 공개 sample 키, 10행씩 나눠 받음 |
| 미국채 2·10년 par yield | 미국 재무부 Daily Treasury Par Yield Curve | 2s10s는 직접 계산 |
| SOFR | 뉴욕연준 | |
| 코스피200, VKOSPI | 한국거래소 지수 사이트 | 현재가·전일 대비만 제공(과거 값 없음) → 1주 변화 '—' |

장별 노트북의 `data/*.json`은 2026-11-09 기준으로 고정되어 있어(결과 재현용), 이 노트북은 `data/note_*` 파일에만 저장합니다. '1주 대비'는 각 출처의 5개 행 전과 비교합니다. 기준금리 계열은 주말도 행이 있어 달력일 5일 전입니다.
#%% code
import marketnote as mn
status = mn.refresh()
for name, s in status:
    print(f"{name:<30s} {s}")
#%% md
## 2. 오늘의 숫자
#%% code
from IPython.display import Markdown, display
rows = mn.table()
display(Markdown(mn.show(rows)))
#%% md
## 3. 노트 틀 (복사해서 `[ ]`만 채우기)
#%% code
print(mn.note_template(rows))
#%% md
## 4. 금요일 주간 정리 질문
- 이번 주 국고 3년과 미국 2년은 각각 몇 bp 움직였나? 같은 방향이었나? (2절 '1주 대비')
- 원/달러가 움직인 이유를 금리 차(한·미 2·3년)로 설명할 수 있나, 아니면 다른 요인(위험 선호, 수급)인가?
- VKOSPI가 오른 주와 내린 주에 코스피200은 어떻게 움직였나? (주가 하락 + 변동성 상승이 같이 오는지)
- 이번 주에 고객(기관·해외)이 물어볼 만한 질문 하나와 내 답 한 줄
#%% md
## 5. 숫자 점검
받은 값이 서로 맞는지, 오래된 값이 아닌지 확인합니다.
#%% code
import csv, io, json
from datetime import datetime, timedelta
import qlcheck
c = qlcheck.Checks("시장노트 숫자 점검")
by = {r["item"]: r for r in rows}
ust = list(csv.DictReader(io.StringIO((mn.DATA / "note_ust_par.csv").read_text())))
last = max(ust, key=lambda r: datetime.strptime(r["Date"], "%m/%d/%Y"))
c.close("2s10s = 재무부 CSV 최신 행의 10년 − 2년 (bp)", by["미국 2s10s(10년 − 2년)"]["value"],
        (float(last["10 Yr"]) - float(last["2 Yr"])) * 100, 1e-9)
today = datetime.now(mn.KST).date()
for name, _, _, label, _ in mn.ECOS_ITEMS:
    d = datetime.strptime(by[label]["day"], "%Y%m%d").date()
    c.true(f"ECOS {label}: 기준일이 10일 안", "오늘 − 기준일 ≤ 10일", (today - d).days <= 10, str(d))
for label in ("코스피 200", "코스피 200 변동성지수"):
    r = next(x for x in json.loads((mn.DATA / ("note_krx_idx_representative.json" if "변동성" not in label else "note_krx_idx_option.json"))
                                   .read_text(encoding="utf-8"))["output"] if x["idx_nm"] == label)
    px, chg = by[label + (" (VKOSPI)" if "변동성" in label else "")]["value"], by[label + (" (VKOSPI)" if "변동성" in label else "")]["d1"]
    c.close(f"KRX {label}: 전일 대비 ÷ 전일 값 = 화면의 등락률 (소수 둘째 자리 반올림 안)", chg / (px - chg) * 100, float(r["idx_fluc_rt"]), 0.006)
c.show();
