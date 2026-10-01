# v5 추가 데이터 계약

schema 2.0에 선택 필드를 추가한다. 기존 프로젝트·run·원본을 덮어쓰는 마이그레이션은 하지 않는다.

- `experiment.interval_proposal`: 알고리즘 버전, 원본 SHA-256, 설정/코드 해시, 전역 시작·끝, 탐색 궤적, fine-start 근거, 불확실성 설명. 프레임은 0 기반이며 끝을 포함한다.
- `start_selection.method=automatic_image_interval`: `confirmed=false`, `release_verified=false`, proposal ID 및 source hash 일치가 필수. 사람 선택은 기존 `human_release_frame`을 유지한다.
- `observation.projected_boundary_px`: 최종 월드 원을 원본 표시 좌표에 투영한 경계. 수동 중심 변경 때 이전 경계는 폐기한다.
- `silhouette_model`: `projected_world_circle`, `pixel_circle`, `manual_pixel_circle`.
- `visible_arc_fraction`: 큰 각도 간격 하나뿐 아니라 36개 방위 구간의 실제 지지를 반영한 비율. 정확도 확률이 아니다.
- `measurement_warning=blurred_edge_review`: 형태 적합이 가능한 흐린 위치는 저장하지만 일반 속도·계수 입력에서 제외한다. 심하게 불일치한 후보는 거부한다.
- `angle_fit_frame_interval`, `angle_fit_samples`: 위치와 독립된 연속 각도 회귀 창. 충돌/관측 gap을 넘지 않는다.
- 사건 `automatic_boundary_proposal`: 위치 변화점의 후보 경계. `boundary_frame_interval`은 실제 전후 회귀 표본에서 사용한 경계다. 사람이 지정한 `contact_frame_interval`과 구분한다.
- 사건 `automatic_fit_gate`: `eligible`, 사유 목록, `scope=automatic_exploratory_not_human_reviewed`, version. kind=isolated_binary, 경계 폭≤2, 전후 각 칩 위치 표본≥5, 법선 σ≤0.08rad, 접근 속도>5σ 조건. 사람 승인 필드를 자동으로 변경하지 않는다. 접선 IFR의 각속도/상태 재구성 요건은 추가 적용한다.
- `normal_trials.a_sigma_m_s`, `b_sigma_m_s`: 충돌 전/후 법선 상대속도의 조건부 σ. 공유 법선 오차를 독립 오차로 확정한 값이 아니다.
- 피팅 입력 `review_scope`: `human_reviewed` / `automatic_exploratory`. `approved`는 피팅 API의 포함 플래그이며 사람이 확인했다는 뜻으로 해석하지 않는다.
- `absolute_accuracy_passed`: 독립 길이 검증 또는 독립 holdout 표기가 있을 때만 인정. 내부 `passed`와 분리한다.
- `physical_properties`, `parent_source_id`, `release_selection`: 계수 출처 기록. 같은 부모 원본을 잘라낸 영상은 독립 검증으로 거부한다.
- `board_view.json`: 배경의 실제 원본 프레임, 보정 상태, 축척/범위, 큰 점은 원본에 보이는 것뿐이라는 설명.
- 진행률 `progress_basis`: 단계/수치 평가 예산 기반. 벽시계 남은 시간 또는 과학 정확도가 아니다.

원본 시간 기준: 표시 순서 frame_index와 PTS/time_base를 유지한다. 프레임 색인은 source hash별 임시 캐시이며 삭제 후 재생성할 수 있다. 동일 프레임의 최종 원본 픽셀 체크섬을 검증하고, 실패 시 원본 순차 디코딩한다.

좌표 기본 계약과 Farkas/IFR 식·부호는 기존 방법 문서를 유지한다. 이번 변경은 관측 추출·창 선택·조건부 오차 전달·적합 절차에 해당한다.
