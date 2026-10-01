# v4.5 추가 데이터 계약

기존 schema 2.0에 `review_schema_version: 1`을 추가한다. 기존 파일을 읽을 때 기본값을 추가하며 원본 과거 결과를 덮어쓰지 않는다.

| 필드 | 의미 |
|---|---|
| experiment.chip_intervals[chip_id] | 정렬된 `{start,end,observable,fit_enabled,reason}` 목록. 정수 프레임, 양쪽 포함, end=null이면 영상 끝. 미지정 칩은 영상 전체 선택 범위를 따름 |
| stop_annotations | stopped=병진·회전 정지 확인, translation_stopped=병진만 정지 확인. 이후 관측을 삭제하거나 속도를 강제로 0으로 만들지 않음 |
| review_history | 구간 수정 시각·이전 값·대상 칩·이유. 구간 표 수정도 기록 |
| row.observable / fit_enabled | 영상 관측 허용과 물리 피팅 허용을 분리 |
| scope_segment / scope_reason | 구간 시작 프레임과 제외/포함 이유. 재진입 전후를 미분·피팅으로 이어 붙이지 않음 |
| position_status / orientation_status | 중심 측정 상태와 방향 측정 상태. 중심이 있어도 방향은 null일 수 있음 |
| manual_plane_locked | 이 영상에 명시한 수동 평면 변환을 자동 재분석에서 보존 |
| event.id | 원본 해시·정렬한 칩 쌍·closest_frame 기반. 후보의 정체가 바뀌면 재검토 |
| event.review_basis | 주변 관측·시간·보정·분석 설정·기하를 묶은 검토 근거 해시 |
| contact_frame_interval | 사람이 고른 마지막 충돌 전/첫 충돌 후 유효 프레임 |
| boundary_frame_interval | 자동으로 제안/정제한 전후 경계. 후보 범위와 구별 |
| unusable_frame_intervals | 양끝 포함의 별도 오염 범위. 유효 기준 프레임과 겹치면 저장 거부 |
| contact_occurrence | actual / none / unknown. ‘피팅 제외’와 ‘비접촉’을 구별 |
| fit_scope_allowed | 사건 양쪽 칩의 해당 범위가 물리 피팅 허용 범위인지 |
| constants.coefficient_status | 계수별 provisional / withheld와 이유·채택 자료 수 |
| validation.evaluated_counts | 실제 유효 점수가 계산된 자유운동 구간/충돌 수. 빈 결과는 검증 완료 아님 |

프레임 31과 32가 유효한 전후 장면이면 미분 절단은 31.5에 둔다. 두 관측 자체는 남는다. 피팅에서 제외한 실제 충돌도 절단한다. 비접촉 사건은 절단하지 않는다.

`quality.observed_fraction_all_target_frames`는 기존 전체 프레임×칩 수 분모를 유지하는 호환 필드다. v4.5의 `observed_fraction_selected_intervals`는 사람이 지정한 칩별 관측 구간만 분모에 넣는다. GUI·요약표에는 후자를 우선 표시한다. 이전 버전과 비교할 때 분모 정의를 확인한다. 관측률은 독립 정답 기반 검출 정확도가 아니다.

기존 IFR 데이터셋 필드 `normal_sigma`는 이름과 달리 **법선 상대속도의 표준편차(m/s)**이며 단위 법선 벡터의 방향각 오차가 아니다. bootstrap에서는 길이/시각 배율을 적용한다. 법선 방향각 자체의 불확실성을 이 필드에 대신 입력하면 안 된다. 물리 허용 범위에 붙거나 식별성이 없는 bootstrap 해는 성공 표본에 넣지 않고 실패 사유를 기록한다.

작업 기록은 실행 완료/중단/실패와 경과시간을 보존한다. 최적화의 모델 평가 횟수는 남은 시간이나 수렴 퍼센트가 아니다. 구간·영상 단위로 확정 가능한 진행률과 구별한다.
