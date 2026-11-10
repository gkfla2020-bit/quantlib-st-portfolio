# 금리·파생 데스크 준비 포트폴리오 (QuantLib 1.44 + Python)

증권사 세일즈앤트레이딩(장외파생·ELS, FICC)을 준비하며 직접 만든 노트북 두 개입니다. 숫자는 모두 실제 실행 결과이고, 공식 무료 자료가 없는 값은 **[예시]**로 표시했습니다.

| 노트북 | 내용 | 독립 점검 |
|---|---|---|
| `notebooks/91_ELS_헤지_프로젝트.ipynb` | 코스피200·HSCEI 스텝다운 ELS(3년, 6개월 조기상환, 낙인 50%)의 몬테카를로 가격, 투자자 수익률 모의실험, 낙인 근처 delta, 10영업일 델타 헤지 손익을 delta·gamma·vega·rho·theta·잔차로 나누기, H지수 급락 경로와 2024년 H지수 ELS 사태(금융감독원 보도자료) 연결 | 9/9 통과 |
| `notebooks/90_매일_시장노트.ipynb` | 한국은행 ECOS(기준금리, KOFR, CD 91일, 국고채 3·10년, 원/달러), 미국 재무부(미국채 2·10년), 뉴욕연준(SOFR), 한국거래소(코스피200, VKOSPI) 최신값 표와 매일 쓰는 노트 틀 | 9/9 통과 |

## ELS 프로젝트에서 확인한 것 (2026-11-09 자료 기준 실행 결과)

- ELS 가치는 원금 100당 90.75(표준오차 0.23)로, 변동성이 오르거나 두 지수의 상관이 낮아지면 떨어집니다. 투자자는 변동성을 판 쪽입니다.
- 위험중립 기준 손실 확률은 19.4%, 손실이 나면 평균 −55.4%입니다. '확률은 낮지만 손실은 큰' 구조라 평균 수익률만으로는 위험이 가려집니다.
- HSCEI delta는 지수가 낙인(50%)에 다가갈수록 커져, 최초 수준 근처의 약 10배(HSCEI 58%에서 208.6)가 됩니다. 헤지 수량이 급하게 바뀌는 구간입니다.
- HSCEI 매도세 **[예시 경로]**에서 10일간 ELS 가치 변화의 대부분은 delta 항이고, 잔차는 실제 변화 합의 5.4%입니다. 델타 헤지 후 하루 손익 크기는 헤지 전의 21.4%로 줄고, 남는 손익은 주로 변동성(vega)에서 나옵니다.

## 모형과 검증

- 위험중립 상관 기하 브라운 운동, 하루 1단계(연 252단계), 낙인은 매일 종가 확인, HSCEI는 원화 지급 퀀토 조정. 그릭스는 같은 난수를 다시 쓰는 재계산(delta ±1%, gamma ±5%).
- 경로 생성기는 3년 ATM 콜을 QuantLib 해석해와 비교해(표준오차 3배 안) 확인했고, 두 지수 하루 수익률 상관(0.6)도 확인했습니다.
- 금리는 국고채 3년(ECOS)을 연속 복리로 바꿔 쓴 **[근사]**, HSCEI 수준·변동성·상관·배당·환율 관련 값과 상품 조건은 **[예시]**입니다. 투자 권유나 실제 상품 가격이 아닙니다.

## 실행하기

QuantLib 1.44, Python 3.13에서 만들었습니다(전체 패키지 목록 `requirements.lock`).

```
python3.13 -m venv .venv
.venv/bin/pip install QuantLib==1.44 numpy pandas matplotlib nbformat nbclient ipykernel pytest
.venv/bin/python -m ipykernel install --user --name ql-study --display-name "QuantLib 1.44 (study)"

# 원자료는 저장소에 넣지 않았습니다. 공식 출처에서 직접 받습니다(data/manifest.json에 URL·받은 시각·SHA-256 기록).
.venv/bin/python tools/fetch_data.py krx_idx_representative krx_idx_option \
    ecos_ktb1y ecos_ktb2y ecos_ktb3y ecos_ktb5y ecos_ktb10y ecos_ktb20y ecos_ktb30y ecos_ktb50y \
    krx_holidays_2026 krx_holidays_2027 fss_hscei_els_20240311 fss_hscei_els_sanction

# 노트북을 원본(extras/*.py)에서 다시 만들고 처음부터 실행해 점검(오류나 '실패'가 있으면 실패로 끝남)
.venv/bin/python tools/make_extras.py --all
.venv/bin/python -m pytest -q tests/
```

자료를 새로 받으면 그날 시세로 다시 계산되므로 숫자가 위와 달라질 수 있습니다. 저장소에 들어 있는 노트북 출력은 2026-11-09 조회 자료(시장노트는 2026-11-10)로 실행한 결과입니다.

## 파일

| 경로 | 내용 |
|---|---|
| `notebooks/els.py` | ELS 상품·시장 정의, 경로 생성, 가격, 그릭스 |
| `notebooks/marketnote.py` | 시장노트 자료 받기, 표, 노트 틀 |
| `notebooks/marketdata.py` | 받은 자료 읽기(KRX 휴장일 달력, 국고채 금리 등) |
| `notebooks/qlcheck.py` | 독립 점검 표 |
| `extras/` | 노트북 원본(`#%% md` / `#%% code`로 셀 구분) |
| `tools/` | 자료 받기, 노트북 생성·실행·점검 |

## 출처

한국은행 ECOS Open API, 미국 재무부 Daily Treasury Par Yield Curve, 뉴욕연준 SOFR, 한국거래소 지수 사이트, 금융감독원 보도자료(2024-03-11 「홍콩 H지수 ELS 검사결과(잠정) 및 분쟁조정기준(안)」, 2026-11-04 「홍콩 H지수 ELS 관련 은행, 증권사 검사 결과 조치」).
