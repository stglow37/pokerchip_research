<!-- V6 DEVELOPMENT -->
# v6 계산·집계 정책

경고와 필수 입력 장벽 분리, 구간/영상/세션 집계, 관측 통합은 [ADR-008](../decisions/ADR-008-v6-warning-and-integration.md)을 따른다. Farkas/IFR 식·부호·단위는 변경하지 않는다. 약한 품질과 수치적 특이성은 같은 조건이 아니다. rank-deficient 피팅 후보는 저장하되 대표계수 집계에서 제외한다. 자동 충돌 포함은 사람이 승인한 것으로 기록하지 않는다.

---

<!-- V5 RELEASE -->
# v5 변경 범위

Farkas/IFR의 물리식·부호·지원 범위는 변경하지 않았다. 자동 구간과 자동 탐색 피팅 포함 기준은 [ADR-007](../decisions/ADR-007-v5-observation-first.md), 추가 데이터 계약은 [V5_DATA_ADDITIONS_KO.md](V5_DATA_ADDITIONS_KO.md)를 따른다. 법선 EIV와 충돌 시각 상태 covariance를 보완했으며, 조건부 불확실성을 독립 정확도라고 표시하지 않는다.

---

# 수학 모델과 구현 결정

버전 1.0.0. SI 내부 단위, world x/y 평면, y 위쪽, 각도·각속도 반시계 양수입니다. 상태는 `[x,y,vx,vy,theta,omega]`입니다. 영상 pixel y는 아래쪽입니다. 입력 논문과 전달 메모는 검토 자료이며, 인쇄식을 무조건 정확하다고 취급하지 않았습니다.

## Farkas 자유운동

전면 원형 접촉, 균일 압력, Coulomb 바닥 마찰을 가정합니다. 질량 m, 반지름 R, 관성 I, μ_b에 대해 ε=|v|/(R|ω|), 힘 `-μ_b m g F(ε) v/|v|`, 토크 `-μ_b m g R T(ε) sign(ω)`이며 g=9.80665 m/s²입니다. θdot=ω, vdot=힘/m, ωdot=토크/I입니다. I는 실측 또는 명시적으로 선택한 균질 원판 `I=.5mR²`만 사용합니다.

K와 E를 modulus k의 완전 타원적분으로 쓸 때, SciPy에는 **parameter m=k²**를 전달합니다. ε≤1:

```
F = 4[(1+ε²)E(ε) − (1−ε²)K(ε)] / (3πε)
T = 4[(4−2ε²)E(ε) + (ε²−1)K(ε)] / (9π)
```

ε>1:

```
F = 4[(1+ε²)E(1/ε) − (ε²−1)K(1/ε)] / (3π)
T = 4ε[(4−2ε²)E(1/ε) + (2ε²−5+3/ε²)K(1/ε)] / (9π)
```

**제공된 2002 preprint의 ε>1 토크 식에는 앞 계수가 4/(9πε)로 인쇄되어 있습니다. 구현은 독립 면적적분과 일치하는 4ε/(9π)를 채택했습니다. 공식 정오표 또는 저자 확인을 확보한 것은 아닙니다.** 전달 패키지의 동일한 인쇄식을 그대로 쓰면 이 구간 토크가 ε²만큼 작아집니다. 균일 원판 위 국소 미끄럼 벡터 `(ε−y,x)`의 정규화 마찰을 직접 적분하여 검산했습니다.

| ε | 독립 면적적분 T | 인쇄된 분모 ε 식 T |
|---:|---:|---:|
| 1.2 | 0.2238467539 | 0.1554491347 |
| 2 | 0.1278091983 | 0.0319522996 |
| 10 | 0.0250208922 | 0.0002502089 |

코드는 ε≈0, ε=1, ε≫1에서 특이점/상쇄를 피하도록 극한과 급수를 분리합니다. `F(0)=0`, `T(0)=2/3`, `F(1)=8/(3π)`, `T(1)=8/(9π)`, `F(∞)=1`, `T(∞)=0`. 순수 병진은 일정 감속과 해석적 정지, 순수 회전은 상수 토크, 혼합은 수치 적분입니다. 작은 정지 기준은 수치 장치이며 실제 stick-slip 정확도를 의미하지 않습니다. 테스트는 독립 polar quadrature, 정지 거리, 에너지, spin 부호, tolerance 수렴을 사용합니다.

출처: [Farkas preprint](https://arxiv.org/abs/physics/0210024), [PRL 논문](https://doi.org/10.1103/PhysRevLett.90.248302), [SciPy ellipk의 parameter 정의](https://docs.scipy.org/doc/scipy/reference/generated/scipy.special.ellipk.html). 제공 PDF는 검토했지만 배포 ZIP에 재수록하지 않았습니다.

## IFR 공통 jump map

법선 n은 칩1 중심→칩2 중심, 접선 t=(-n_y,n_x). 접근 속도 a=(v1−v2)·n>0, 접촉점 미끄럼 c=(v1−v2)·t+R1ω1+R2ω2입니다. **두 spin을 모두 포함**합니다.

```
A_n = 1/m1 + 1/m2
A_t = A_n + R1²/I1 + R2²/I2
J_n = (1+e_n)a/A_n
J_te = (1+e_t)c/A_t
J_f = sign(c) min(μ_c J_n, |c|/A_s)
J_t = J_te + J_f
v1+ = v1− − (J_n n + J_t t)/m1
v2+ = v2− + (J_n n + J_t t)/m2
ω1+ = ω1− − R1 J_t/I1
ω2+ = ω2− − R2 J_t/I2
```

- `contact_consistent_reconstruction`: A_s=A_t. 임의 초기 spin에 대한 접촉 속도 기반 수학적 확장입니다. 이 확장의 실험 검증은 대기입니다.
- `percussion_paper_scope`: A_s=2A_n. 원문의 무초기회전·균질 원판 범위로 제한합니다. 초기 spin 또는 다른 관성이 들어오면 `unsupported`입니다. 인쇄된 모든 질량비 오류를 그대로 복제하는 모델이 아니라, 공통 impulse 보존식으로 재현한 원문 제한 분기입니다.

관측 접선 비는 `e_t_obs = −c+/c = e_t + A_t J_f/c`입니다. e_t와 e_t_obs는 다릅니다. contact sticking에서는 1+e_t, percussion sticking에서는 1.5+e_t입니다. c≈0에서는 null로 둡니다. μ_c=0이어도 e_t가 −1이 아니면 접선 충격량이 남습니다. 마찰 없는 접선 impulse zero 테스트는 μ_c=0, e_t=−1을 사용합니다.

| 제공 IFR PDF의 부분 | 검토 결과와 채택 |
|---|---|
| 식(3) 앞 I=mR/k 표기 | 차원상 I=mR²/k 채택 |
| 식(10)의 입사체 마찰 속도항 M | J/m1으로 유도. 입사체 항에 불필요한 M을 넣지 않음 |
| 식(14)의 표적 속도 M 누락 | J/m2로 질량비 적용 |
| 식(24)의 접촉 전이 /(1+e_t) | 공통 마찰 impulse 포화 경계로 선택. 다른 분기 경계와 섞지 않음 |
| 식(33)의 접선 부호/M | 위 signed impulse 공통식 사용 |
| 식(29)의 정지 거리 비 | Farkas 혼합운동의 보편 정지 거리 식으로 사용하지 않음 |

이 표는 제공 원문·전달 노트·보존식의 비교로 내린 구현 결정이며 논문 저자의 공식 수정이라고 주장하지 않습니다. 출처: [IFR 논문 DOI](https://doi.org/10.1063/5.0044963).

## 물리 허용성과 사건 적분

0≤e_n≤1, −1≤e_t≤1, μ_c≥0을 요구하고 각 충돌에서

`ΔK = −aJ_n + .5A_nJ_n² − cJ_t + .5A_tJ_t²`

를 계산합니다. total K가 증가하는 계수 조합은 `invalid`; 속도를 재조정하여 숨기지 않습니다. 전체 선운동량과 임의 원점의 궤도+spin 각운동량을 검산합니다. 병진 에너지만 증가하는 것은 spin에서 전달된 경우 가능하므로 total을 씁니다.

자유운동 사이에서 원판 간 gap의 첫 접근 root를 찾고, step 양끝이 비접촉이어도 중간 최소 gap/swept 후보를 검사합니다. 충돌 시 모든 칩 상태를 같은 시각으로 이동하고 x/θ를 연속으로 보존한 채 v/ω만 jump합니다. separating pair에 impulse를 반복하지 않습니다. 동시 다중접촉·지속 접촉·3D 이탈에는 임의 쌍 순서나 큰 위치 보정을 적용하지 않습니다.

순간 충돌 동안 바닥 impulse와 rolling couple은 기본 모델에서 무시합니다. 실제 접촉 지속시간이 확보되면 μ_bmgΔt_c와 J_n/J_t를 비교해야 합니다. rolling 계수·환형 압력·속도 의존 마찰·진짜 다체 접촉은 이 버전의 확정 모델이 아닙니다.

## 관측·불확도·피팅

경계 원 피팅의 공분산은 조건부 국소 근사입니다. 부분 가림의 편향이나 잘못된 경계를 포함한 전체 정확도 보증이 아닙니다. 세계 원을 원본 영상에 재투영해 경계 샘플을 갱신하되 원본 grayscale에서 계측합니다. 반경 prior는 후보/적합 진단용이며 실측 반지름을 대신하지 않습니다.

운동학은 불균일 물리 시각의 가중 국소 2차 다항식입니다. 충돌·발사 제외 구간·결측을 가로지르지 않습니다. unwrapped 각은 연속 유효 구간 내 gauge를 유지하되 alias 상한 조건에 의존합니다. 물리 시간이 미확정이면 속도·각속도·가속도는 null입니다.

사건 시각은 한쪽 위치 외삽의 접촉·연속성을 최소화한 추정치입니다. 전후 위치 적합, 반지름 sigma, 선택적 `shared_scale_sigma_fraction`과 `event_clock_sigma_s`를 선형화해 시간/법선 오차를 계산합니다. 반지름 sigma가 없으면 2% 임시값을 썼다는 이름을 결과에 표시합니다. 사용자 제공 공통 scale/clock sigma가 0이면 그 오차가 알려져 0이라는 뜻이 아니라 입력되지 않은 조건부 결과입니다. 비선형/가림/모델 오차 전체 coverage는 미검증입니다. 별도 `monte_carlo` 함수는 공통 session draw와 독립 draw를 분리합니다.

피팅은 μ_b→e_n→e_t/μ_c 순서, robust loss와 접선 multistart, trial별 초기 상태와 공통 계수 분리, 전후 상태 EIV, whole trial/session bootstrap을 사용합니다. `shared_scale_sigma_fraction`은 bootstrap에서 세션별 공통 scale draw입니다. Jacobian rank/조건·상관·경계·sticking-only 상태를 출력합니다. 정규근사 공분산은 조건부이며 optimizer 성공이 물리·식별·실험 타당성 성공을 뜻하지 않습니다. e_t/μ_c가 좁은 조건에서 구분되지 않으면 추가 조건이 필요합니다.

free-motion / impact-conditional / full-forward 평가는 분리합니다. RMSE/MAE는 각 물리 단위별 성분 평균이며 2차원 거리 norm의 RMS와 다릅니다. coverage95는 입력 sigma에 대한 조건부 잔차 비율입니다. 실제 반복실험 coverage와 시간/기하 오차를 포함한 계수 정확도는 실측 검증 전 확정하지 않습니다.
