# v2 물리·피팅 검토 기록

## Farkas

전면 원형 접촉, 균일 압력, 일정한 등방 Coulomb 마찰을 기준 모델로 유지합니다. 상태 `[x,y,vx,vy,theta,omega]`, world y 위쪽, CCW 양수, 내부 SI 단위도 유지합니다. 물체가 원처럼 보인다는 사실은 실제 접촉 압력이나 관성분포가 균일하다는 증거가 아닙니다.

v1의 epsilon>1 토크 재구성은 독립 원판 면적적분·극한·정지거리·에너지·수렴 검사를 유지해 확인합니다. 이 판단을 저자의 공식 정오표로 표시하지 않습니다. 식과 채택 이유는 `MODEL_DECISIONS_KO.md`에 있습니다. 이번 수정은 이 식을 다른 경험식으로 교체하지 않았습니다.

추가한 검사는 무한/NaN 계수·시간·상태와 잘못된 수치 tolerance를 거부하는 것입니다. 물리적으로 설명되지 않은 오차를 friction parameter 하나로 숨기지 않도록 직접 관측과 모델 예측을 분리합니다.

## IFR

법선은 칩1→칩2, 접선은 `(-ny,nx)`입니다. 상대 접근 `a=(v1-v2)·n`, 접촉점 미끄럼 `c=(v1-v2)·t+R1ω1+R2ω2`를 사용합니다. `J_n`, `J_te`, `J_f`, `J_t`와 spin 변화는 v1 보존식 재구성을 유지했습니다.

기존 `branch=sticking`은 **마찰 성분 J_f가 포화 상한에 도달한 분기**입니다. 접선 복원 성분을 더한 후의 전체 접촉점 속도 `c_after`가 반드시 0인 것은 아닙니다. v2는 이 의미를 `branch_definition`과 `contact_slip_after_m_s`로 명시합니다. 입력 `e_t`와 관측 `e_t_obs=-c_after/c`도 구분합니다.

`contact_consistent_reconstruction`은 초기 spin을 포함하는 수학적 확장이며 실제 칩으로 검증된 보편 법칙이라는 주장이 아닙니다. `percussion_paper_scope`는 무초기회전·균질원판에 제한됩니다. 바닥 impulse와 유한 접촉시간은 포함하지 않습니다. 계수로 total energy가 증가하면 물리 허용 실패로 남깁니다.

## 피팅

`μ_b → e_n → (e_t, μ_c)`의 단계형 구조를 유지합니다. free-motion은 위치·각도에 직접 맞추고 trial별 초기상태를 nuisance로 추정합니다. impact EIV는 전 상태 측정오차를 반영합니다.

수정한 오류:

1. 정상속도 피팅에서 입력 법선을 정규화하여 접선 solver와 일치시킴.
2. 최종 접선 진단을 원래 pre-state가 아니라 최적 EIV pre-state로 다시 계산.
3. sigma≤0, NaN과 잘못된 공분산을 조용히 사용하지 않고 거부.
4. 계수 적용 시 normal/tangential optimizer 성공도 확인.
5. bootstrap에서 공통 scale과 clock 변화에 맞게 관측·초기상태·sigma·공분산을 함께 변환.
6. 사건 추출에서 계산한 velocity/omega sigma를 피팅 입력으로 전달.

선택적 covariance 입력은 `position_angle_covariance` (3×3 또는 N×3×3), `pre_covariance`/`post_covariance` (3×3 또는 2×3×3)입니다. 충돌 성분 순서는 `[vx,vy,omega]`입니다. 관측 내 성분 상관을 Cholesky whitening으로 처리합니다. 시간적으로 상관된 전체 영상의 공분산을 구성하는 구현은 아닙니다.

whole-session bootstrap은 프레임 간 상관을 보존하는 cluster resampling입니다. supplied shared scale/clock만 추가로 샘플링합니다. 작은 세션 수나 적은 bootstrap 반복에서 좁은 CI가 나왔다고 높은 정확도를 보장하지 않습니다. 관성·렌즈 왜곡·모델 불일치가 자동으로 모두 포함되지는 않습니다.

## 식별성과 예측 검증

국소 Jacobian, 조건부 covariance, parameter correlation, active bounds, sticking-only 상태를 유지합니다. v2의 접선 profile은 한 계수를 고정한 뒤 다른 계수와 EIV 전 상태를 다시 최적화합니다. e_n은 단계 추정값으로 고정됩니다. robust 비용 차이는 일반적인 likelihood-ratio 신뢰구간이 아니므로 `confidence_interval=null`로 저장합니다.

fit 결과에는 optimizer 성공, 물리 허용, 국소 식별, holdout 평가 여부가 분리되어 있습니다. holdout 합격 여부는 사용자의 물리 허용오차가 정해지기 전 `null`입니다. 최종시험 세션은 학습·모델선택 보류와 중복을 거부합니다.

## 실제 모델 검증에 필요한 다음 실험

- 단일 검정 칩: 다양한 초기 속력/회전, 바닥 위치·진행방향 반복
- 정상 충돌: 접근속도 범위와 chip pair 반복
- 접선 충돌: `c/a`의 양·음, 넓은 범위, 초기 spin 양·음
- 다른 촬영일/session 전체를 보류하고 완전 전방 궤적 비교
- 측정 `m,R,I`의 오차와 촬영 scale/clock의 오차 기록

이 실험으로 잔차가 속도·위치·방향에 따라 반복되는 것이 확인되면 그때 대안 마찰/반발 모델을 추가하는 것이 합리적입니다.
