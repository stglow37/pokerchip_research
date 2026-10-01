# ADR-006: v4.5 검토·계산 계약

- 상태: 채택
- 결정일: 2026-09-30
- 통합일: 2026-10-01

사용자 요청에 따라 구간·충돌 검토·계수 작업·GUI를 함께 개선한다. 기존 물리 지배식은 유지하고 단위/독립 적분/보존 시험으로 검산한다.

## 변경 전 writer/reader
- project.json: core/config, core/migration, core/storage; UI forms/review_base/main_window; application automatic.
- SQLite observations/manual/trajectories/events: application/pipeline가 writer, analysis/quality, application/exporting 및 models/study/research, UI review_base가 reader.
- 계수/검증 JSON: models/study와 fitting이 writer, UI 및 compare_forward가 reader.
- 외부 CSV: application/exporting 및 models/study. 기존 필드는 보존하고 새 상태 필드를 추가한다.

## 계약
기존 schema 2.0을 파괴하지 않는 추가형 review_schema_version=1을 도입한다. chip_intervals는 칩별 포함 범위이며 구간 밖을 속도 0으로 바꾸지 않는다. stop_annotations는 정지 확인 주석으로, 이후 접촉에서 칩을 제거하지 않는다. 물리용 범위와 관측용 범위를 구분한다.

충돌의 last_pre_frame/first_post_frame은 유효 표본이고, 그 사이에 미분 절단선을 둔다. unusable_frame_intervals만 관측 제외 구간이다. 피팅 제외와 비접촉은 다르다. 사건 ID/검토 근거를 원본·칩·측정에 연결하며 오래된 승인을 다른 사건에 옮기지 않는다.

작업 취소는 협력적이며 잔차 평가 전후·영상/구간 경계에서 확인한다. 반복 최적화 평가 횟수는 수렴 퍼센트가 아니다. 검증 완료는 실제 계산된 유효 점수 수로 판정한다.

## 검증
2.0 읽기·round-trip·반복 migration, 정지 후 재충돌, 칩별 이탈, 양쪽 유효 경계 보존, 제외된 실제 충돌, 빈 검증, 클릭 프레임 불일치, 취소·진행 이벤트를 회귀 시험으로 추가한다. 실제 영상 시험은 합성 물성 복원과 별도 기록한다.
