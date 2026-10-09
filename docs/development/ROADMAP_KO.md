# 2026-10-10 추가 연구 범위

사용자가 요청한 전체 영상 감사에 맞춰 후반 격자 복구 및 별도 마찰장 후보 API를 구현·시험했다. 자동 처리와 독립 계측 정확도를 구분한다. 기존 장기 로드맵과 기본 물리식은 유지한다.

---

<!-- V6 DEVELOPMENT -->
# 사용자 우선순위: v6 분석·통합

공통 사용 가능/경고 판정 및 표시 → 구간별 마찰·사건별 충돌 집계 → 신뢰도·고정 검증 → 제출 검사 및 새 통합 프로젝트의 구현과 소프트웨어 인수를 마쳤다. 상세 결정은 [ADR-008](../decisions/ADR-008-v6-warning-and-integration.md), 근거는 [v6 요구사항](V6_REQUIREMENTS_KO.md)과 실행 기록을 따른다. 전체 198개 시험 통과. 다음 연구 단계는 독립 촬영 세션 검증이며, 기존 Phase 2 기본 작업보다 이 명시적 요청을 우선했다.

완료 조건은 경고만 달라진 관측의 숫자 일치, 필수 입력/모델 장벽 유지, 최종 계수까지의 실제 원인 프레임 전달, 구간/계층 집계, 재표본 재현성, 학습/검증 누수 및 제출 충돌 검사, 실제 ZIP 비교, 전체 pytest·GUI·내보내기 증거와 문서 인수다. 최적화 성공을 물리 정확도로 설명하지 않는다.

---

<!-- V5 RELEASE -->
# v5 개발 상태

구현 범위 및 미입증 범위는 [V5_REQUIREMENTS_KO.md](V5_REQUIREMENTS_KO.md)에 항목별로 기록했다. 다음 단계는 새로운 영상의 독립 검증이다. 추가 GUI/알고리즘 튜닝은 검증군을 개발군으로 전환하므로 평가군을 따로 보존한다. 아래 v4/v4.5 계획은 이력이다.

---

<!-- V45 RELEASE -->
# v4.5 적용 상태

사용자가 요청한 v4.5 작업의 현 상태는 [요구사항 대응표](V45_REQUIREMENTS_KO.md)와 [검증 기록](../../validation/test-records/v45/REPORT_KO.md)에 있다. 아래 Phase 순서는 v4 정리 당시 계획이다. 이번에는 schema를 통째로 교체하지 않고 추가형 검토 계약으로 호환성을 유지했다. 속도 의존 마찰·임의 다체 충돌을 검증 없이 새 확정 모델로 추가하지 않았다.

---

# 발전 로드맵과 완료 조건

이 문서는 남은 작업의 권장 순서다. 사용자가 우선순위를 바꿀 수 있지만, 한 패치에서 여러 단계의 schema·UI·물리 변경을 섞지 않는다.

## Phase 0 — 기준선 동결: 완료

목적: 원본 v4, 활성 정본, 결과 schema와 자동 시험 기준을 보존한다.

완료 근거:

- v4.0.0 ZIP과 manifest 동결
- 저장소 구조 재편 후 116개 시험 통과 기록
- 결과 요약·증거와 ZIP 대응 확인

## Phase 1 — 데이터 무결성 P0: 자동 기준 완료

목적: 잘못된 캐시 재사용, 사건 장벽, 수정 의존성, 비동기 결과 연결, 법선/IFR 결측 결합을 수정한다.

완료 근거:

- [PHASE1_DATA_INTEGRITY_20260930_KO.md](../../validation/test-records/PHASE1_DATA_INTEGRITY_20260930_KO.md)
- 최신 전체 126개 시험 통과

실제 물리 정확도 검증은 Phase 4와 7에서 계속한다.

## Phase 2 — Schema 3.0과 artifact 의존성

목적: 데이터 의미와 무효화 관계를 명시하여 이후 CLI·GUI가 같은 계약을 사용하게 한다.

범위:

- 현재 writer/reader와 schema 2.0 fixture 인벤토리
- 칩별 유효 구간과 이유
- position/orientation/identity/time/geometry 채널별 품질
- 안정 사건 ID와 후보/경계/검토 상태
- Measurement/Derived/Physics/Validation/Presentation artifact 참조와 hash
- 2.0→3.0 추가형 migration

완료 조건:

- 기존 2.0 프로젝트와 run을 손실 없이 읽는다.
- migration은 반복 실행해도 같은 결과를 낸다.
- 이전 CLI/import/공개 필드는 유지된다.
- 어떤 변경이 어떤 artifact를 무효화하는지 단위시험으로 고정한다.
- schema와 데이터 사전이 동시에 갱신된다.

## Phase 3 — 측정·검토 workflow

목적: 유효 운동 구간과 사건 경계를 사람이 원본 영상과 대조해 일관되게 승인할 수 있게 한다.

범위:

- 칩별 launch/end/exit/re-entry/occlusion interval
- 접촉 전후 경계와 사용 불가 범위 편집
- 수동 중심·ID·각도 수정의 채널별 stale/recompute
- review spec의 저장·재적용
- 자동 제안과 사람 승인의 명확한 구분

완료 조건:

- 같은 review spec을 CLI와 GUI가 동일하게 적용한다.
- 수정 뒤 영향받는 파생량만 무효화된다.
- 가림·이탈·재충돌 fixture가 사건/운동학 창을 오염시키지 않는다.

## Phase 4 — 물리·피팅과 독립성

목적: `mu_bottom`, `e_normal`, IFR 계수의 자격·식별성·불확실성·검증 범위를 분리한다.

범위:

- 계수별 eligibility와 skipped reason
- normal/IFR release gate
- session 단위 bootstrap과 calibration/time 공통오차
- sticking-only와 active-bound 식별 진단
- 학습/검증 원본 해시·session 중복 차단
- 고정 계수 holdout과 새 독립 영상 평가

완료 조건:

- 자료 부족 시 계수를 만들지 않고 이유를 저장한다.
- 후속 단계가 앞 단계 계수를 몰래 재피팅하지 않는다.
- 합성 계수 복원과 독립 실제 영상 결과를 별도 보고한다.

## Phase 5 — CLI 우선 사용 흐름과 선택적 GUI

목적: 영상 한 개와 최소 설정으로 시작할 수 있는 CLI를 제공하고 GUI는 같은 서비스를 쓰는 편집·검토 도구로 유지한다.

범위:

- `analyze-video VIDEO --project/--output` 수준의 간편 흐름 설계
- dry-run/preflight와 필요한 사용자 조치 출력
- machine-readable progress, exit code, resume/cancel
- CLI/GUI 공통 request/result DTO 또는 application service
- GUI의 물리 계산 제거 여부 재감사

완료 조건:

- 동일 입력·review spec으로 CLI와 GUI 산출물 schema/hash가 일치한다.
- headless 환경에서 GUI 없이 분석·검토 파일 생성·재실행이 가능하다.
- 고급 기능은 기존 명령과 호환된다.

## Phase 6 — 산출물과 문서

목적: 숫자뿐 아니라 단위, 상태, 근거, 미산출 사유를 한 결과 묶음에서 읽게 한다.

범위:

- observation/derived/prediction 구분
- 시간·거리·회전 검증 상태와 모델 버전 표시
- 계수별 eligibility/skipped reason
- 상대 링크·이미지 검사
- 사람용 요약과 machine-readable manifest 일치

완료 조건:

- 모든 그래프 축과 표 필드에 단위가 있다.
- null과 미산출 이유가 export에서 보존된다.
- 보고서 링크와 동결 근거가 자동 검사된다.

## Phase 7 — 검증과 출시

목적: 소프트웨어 회귀와 실제 연구 타당성을 구분해 릴리스한다.

검증 층:

- 단위: 수식, interval algebra, migration, hash projection
- 통합: CLI/GUI 공통 서비스와 결과 schema
- 합성 E2E: 관측, 사건, 계수, 고정 예측
- 실제 영상: 가림, 이탈, 정지, 재충돌, 혼합 fps
- 운영: 취소, 재개, 디스크 부족, 원본 이동, 손상 DB
- Windows UX: DPI 100/125/150/200%, 키보드, 긴 한국어
- 연구 독립성: 새 날짜/session과 독립 시간·기하 기준

완료 조건:

- 지원 Python 환경과 Windows 설치 경로에서 전체 시험 통과
- 알려진 미검증 범위를 릴리스 문서에 명시
- 동결 artifact, manifest, 변경 기록, 재현 명령 제공

## 공통 중단 조건

다음 상황에서는 값을 추측하거나 범위를 넓히지 말고 사용자 결정을 요청한다.

- 기존 외부 schema의 의미를 바꿔야 하는 경우
- 물리식 또는 논문 해석을 바꿔야 하는 경우
- 실제 데이터가 없어 합격 기준을 정할 수 없는 경우
- 원본·동결 artifact 삭제나 재생성이 필요한 경우
- 서로 다른 단계의 변경을 한 패치에 결합해야만 진행되는 경우
