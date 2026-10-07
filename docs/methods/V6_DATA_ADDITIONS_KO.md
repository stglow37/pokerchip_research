# v6 추가 데이터 계약

schema 2.0 유지. 기존 필드는 삭제하지 않는다. 아래 필드는 선택적이며 구형 결과에 없다고 0으로 추측하지 않는다.

## 경고 전달

- `calculation_status`: computed / computed_with_warnings / not_computed. 미터 계산은 불가하고 픽셀 계산이 되는 경우 partially_computed / partially_computed_with_warnings다. 관측의 `status`와 별개다.
- `metric_calculation_status`, `pixel_calculation_status`, `pixel_warning_audit`: 미터/픽셀 운동학의 상태와 픽셀 입력 경고. 미터 입력이 없다고 계산된 픽셀 결과를 미산출로 숨기지 않는다.
- `calculation_warnings`: 관측 품질과 계산 진단 사유 목록.
- `used_observation_refs`: 실제 의존 관측의 `{chip_id, frame_index}` 합집합.
- `warning_observation_refs`: 위 관측 중 경고가 있는 `{chip_id, frame_index, reasons}`. 전체 계수에서는 `video_id`도 기록한다.
- `used_observation_count`, `warning_observation_count`, `warning_observation_fraction`, `uses_warned_observations`: 중복 칩/프레임을 제거한 수와 비율. 회귀 대상 프레임 자체에 경고가 없어도 주변 경고 관측의 영향을 받을 수 있다.
- `angle_warning_audit`: 회전 회귀만의 의존 관측. 위치와 회전은 부분 계산을 허용한다.
- 사건의 `automatic_fit_gate`: eligibility의 hard blockers와 soft warnings. 승인되지 않은 자동 탐색 입력은 `review_scope=automatic_exploratory`다.
- IFR trial의 `approved`는 사람 승인만 뜻한다. 자동 입력은 approved=false, calculation_eligible=true로 탐색 피팅에 들어간다. 일반 승인 전용 피팅과 구별한다.

## 계수와 불확실성

`constants.json`에는 기존 `parameters`, `parameter_hash`, `training_sources`, `stages`, `data`, `coefficient_status`를 유지한다.

- `segment_estimates`: 프레임 구간, 추정 μ_b, 조건부 분산, 초기 상태·수렴·식별성·경계 진단, 위치/각도 피팅 잔차, 경고 참조, 실행 시간(초).
- `stages.free_motion.aggregation`: 영상/세션 평균과 분포, 대표값, 중앙값, 표준편차, 조건부 역분산 평균. 대표값은 영상과 세션에 동일 가중치다.
- `data.normal_trials`: 전후 접근/분리 속도(m/s), 각각의 조건부 sigma, 원 관측 `e_n_obs=-b/a`. 범위 밖 원값을 잘라내지 않는다.
- `collision_estimates`: 접선 접촉속도(m/s), 관측 접선 비, 회전 변화(rad/s), 병진/회전 채널별 접선 충격량(N·s), 일관성 잔차. 단일 사건의 독립 e_t/μ_c 추정이 아니다.
- `reliability`: cluster unit, scope, 요청/성공 재표본 수, seed, 95% percentile 구간, 실패 사유, 영상 하나씩 제외한 대표값. 표본 수 하나는 interval95=null.
- `tangential_bootstrap`: 고급 전체 단계 재피팅, 기본 disabled. 제공된 공통 scale/clock 상대 sigma만 샘플링한다.
- `coefficient_status`: 계수별 사용 구간/사건 수, 영상 수, 세션 수, 경고 관측 수·비율, 보류 사유. 숫자의 존재는 독립 정확도 검증이 아니다.

`구간별_마찰계수.csv`, `충돌별_계수.csv`, `계수_신뢰도.csv`는 JSON 세부 기록의 평탄 요약이다. 빈칸은 0이 아니다. 피팅 잔차, 재표본 구간, 고정 holdout 예측오차는 서로 다른 지표다.

## 통합

`submission.json`: 분석자 ID, 제출 생성 시각, experiment ID→채택 run 경로. project/run 스냅샷·관측 DB·사건·수정 이력과 함께 전달한다.

`integration_report.json`: 모든 제출본의 출처, 중복·검토 차이, 채택/명시적 제외, 미해결 항목, 원래/새 experiment와 run 대응, 새 계수 경로. 동일 원본 SHA→채택 key와 `__exclude__` key 목록은 명시적 통합 결정이다.

가져온 run의 `imported_manifest.json`은 원래 provenance다. 새 manifest는 가져오기 출처 및 새 프로젝트 의존성을 기록한다. 칩/사건 ID는 영상 내부에서 유지하고 experiment/run namespace로 제출본을 구별한다.
