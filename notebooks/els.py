"""두 기초자산(코스피200, HSCEI) 스텝다운 ELS의 몬테카를로 가격과 그릭스.

- 기초자산은 '최초 기준가 대비 비율'(1.0 = 100%)로 다룬다. ELS 지급액이 비율에만 달려 있기 때문이다.
- 경로는 상관된 기하 브라운 운동(위험중립), 하루 1단계(연 252단계), 낙인(KI)은 매일 종가로 확인한다.
- 같은 정규난수(Z)를 모든 재계산에 다시 써서(공통 난수) 그릭스와 날짜별 가치 차이의 잡음을 줄인다.
- 금리·배당·변동성은 상수(평평), HSCEI는 원화로 지급하는 퀀토라 드리프트에서 ρ(HSCEI, 환율) × σ_H × σ_FX 를 뺀다.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np


@dataclass(frozen=True)
class StepDown:
    notional: float = 100.0                                    # 원금 100 기준
    years: float = 3.0
    obs_per_year: int = 2                                      # 6개월마다 조기상환 평가
    barriers: tuple = (0.90, 0.90, 0.85, 0.85, 0.80, 0.75)     # 각 평가일의 상환 조건(최초 대비)
    coupon: float = 0.07                                       # 연 수익률(조기상환·만기 상환 때)
    ki: float = 0.50                                           # 낙인 수준
    steps_per_year: int = 252

    @property
    def n_steps(self) -> int:
        return int(round(self.years * self.steps_per_year))

    @property
    def obs_steps(self) -> list[int]:
        k = self.steps_per_year // self.obs_per_year
        return [k * (i + 1) for i in range(len(self.barriers))]


@dataclass(frozen=True)
class Market:
    r: float                                                   # 원화 할인 금리(연속 복리)
    q: tuple = (0.015, 0.035)                                  # 배당수익률(코스피200, HSCEI)
    vol: tuple = (0.30, 0.30)                                  # 변동성
    rho: float = 0.6                                           # 두 지수 상관계수
    quanto: tuple = (0.0, 0.0)                                 # ρ(지수, 원화환율) × σ_지수 × σ_환율


def normals(n_pairs: int, n_steps: int, seed: int = 20261110) -> np.ndarray:
    """(2 × n_pairs, n_steps, 2) 표준정규난수. 뒤 절반은 앞 절반의 부호를 바꾼 것(antithetic)."""
    z = np.random.default_rng(seed).standard_normal((n_pairs, n_steps, 2)).astype(np.float32)
    return np.concatenate([z, -z], axis=0)


def simulate(perf0, mkt: Market, z: np.ndarray, dt: float) -> np.ndarray:
    """현재 비율 perf0=(p1, p2)에서 시작한 경로. 결과 (n_paths, n_steps, 2), 첫 열은 다음 날."""
    e1 = z[..., 0]
    e2 = mkt.rho * z[..., 0] + np.sqrt(1 - mkt.rho ** 2) * z[..., 1]
    out = np.empty(z.shape, dtype=np.float64)
    for i, e in enumerate((e1, e2)):
        drift = (mkt.r - mkt.q[i] - mkt.quanto[i] - 0.5 * mkt.vol[i] ** 2) * dt
        out[..., i] = perf0[i] * np.exp(np.cumsum(drift + mkt.vol[i] * np.sqrt(dt) * e, axis=1))
    return out


def pv_paths(prod: StepDown, mkt: Market, perf0, elapsed: int, ki_hit: bool, z: np.ndarray):
    """경로별 현재가치와 결과 구분. elapsed = 발행 후 지난 영업일 수(아직 조기상환 안 된 상태라고 가정)."""
    dt = 1 / prod.steps_per_year
    rem = prod.n_steps - elapsed
    paths = simulate(perf0, mkt, z[:, :rem, :], dt)
    worst = paths.min(axis=2)
    n = worst.shape[0]
    pv = np.zeros(n)
    outcome = np.full(n, -1)                                   # k: k번째 평가일 상환, 99: 만기 KI 없음, 100: 손실
    alive = np.ones(n, dtype=bool)
    for k, (s, b) in enumerate(zip(prod.obs_steps, prod.barriers)):
        if s <= elapsed:
            continue
        j = s - elapsed - 1
        hit = alive & (worst[:, j] >= b)
        t = (s - elapsed) * dt
        pv[hit] = prod.notional * (1 + prod.coupon * (k + 1) / prod.obs_per_year) * np.exp(-mkt.r * t)
        outcome[hit] = k
        alive &= ~hit
    T = rem * dt
    ki = ki_hit | (worst.min(axis=1) < prod.ki)
    full = alive & ~ki
    loss = alive & ki
    pv[full] = prod.notional * (1 + prod.coupon * prod.years) * np.exp(-mkt.r * T)
    outcome[full] = 99
    pv[loss] = prod.notional * worst[loss, -1] * np.exp(-mkt.r * T)
    outcome[loss] = 100
    return pv, outcome, worst


def price(prod: StepDown, mkt: Market, perf0=(1.0, 1.0), elapsed: int = 0, ki_hit: bool = False, z=None):
    """(가치, 표준오차). 표준오차는 antithetic 쌍의 평균으로 계산."""
    pv, _, _ = pv_paths(prod, mkt, perf0, elapsed, ki_hit, z)
    half = len(pv) // 2
    pair = 0.5 * (pv[:half] + pv[half:])
    return float(pv.mean()), float(pair.std(ddof=1) / np.sqrt(half))


def greeks(prod: StepDown, mkt: Market, perf0, elapsed: int, ki_hit: bool, z, h: float = 0.01, h_gamma: float = 0.05) -> dict:
    """공통 난수로 다시 계산한 그릭스. delta_i = ∂V/∂p_i (p = 최초 대비 비율, ±h로 중앙 차분),
    gamma·cross gamma는 같은 단위이되 ±h_gamma로 구한다(조기상환·낙인 조건이 계단 모양이라 작은 움직임으로는 잡음이 큼).
    vega_i = 변동성 1%p 당, rho = 금리 1bp 당, theta = 하루 지날 때 가치 변화."""
    P = lambda p=perf0, m=mkt, e=elapsed: price(prod, m, p, e, ki_hit, z)[0]  # noqa: E731
    v0 = P()

    def bumped(a, b):
        return P((perf0[0] * (1 + a), perf0[1] * (1 + b)))
    out = dict(value=v0,
               delta=((bumped(h, 0) - bumped(-h, 0)) / (2 * perf0[0] * h), (bumped(0, h) - bumped(0, -h)) / (2 * perf0[1] * h)))
    g1, g2 = perf0[0] * h_gamma, perf0[1] * h_gamma
    out["gamma"] = ((bumped(h_gamma, 0) - 2 * v0 + bumped(-h_gamma, 0)) / g1 ** 2,
                    (bumped(0, h_gamma) - 2 * v0 + bumped(0, -h_gamma)) / g2 ** 2)
    out["cross"] = (bumped(h_gamma, h_gamma) - bumped(h_gamma, -h_gamma) - bumped(-h_gamma, h_gamma)
                    + bumped(-h_gamma, -h_gamma)) / (4 * g1 * g2)
    out["vega"] = tuple(P(m=replace(mkt, vol=tuple(v + (0.01 if i == j else 0) for j, v in enumerate(mkt.vol)))) - v0 for i in range(2))
    out["rho"] = P(m=replace(mkt, r=mkt.r + 1e-4)) - v0
    out["theta"] = P(e=elapsed + 1) - v0 if elapsed + 1 < prod.n_steps else 0.0
    return out
