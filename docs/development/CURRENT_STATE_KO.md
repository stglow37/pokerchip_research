# 6.0.0+audit1 연구용 로컬 개선본 (2026-10-10)

후반 격자 재탐색과 에너지 소산 조건을 지키는 원형 접촉 마찰장 후보를 추가했다. 기본 Farkas/IFR 경로와 schema 2.0은 유지한다. 전체 207개 시험 통과(86.42초), 독립 물리 정확도 인증과 구분한다. 상세 사용법은 [AUDIT1](../operations/AUDIT1_KO.md), 결정은 ADR-009/010, 실행 로그는 validation/test-records/audit1이다. 전체 실영상 연구 결과는 코드 폴더 밖의 분석 보고서를 따른다.

---

<!-- V6 DEVELOPMENT -->
# v6.0.0 현재 상태 (2026-10-07)

`codex/analysis-quality-and-coefficient-integration`에서 경고 포함 계산, 모든 적격 구간별 마찰 피팅, 사건별 법선/접선 진단, 계층 집계·재표본, 제출 검사·새 프로젝트 통합의 구현과 소프트웨어 인수 확인을 마쳤다. 물리식과 schema 2.0을 유지한다. 개발 당시에는 main 병합을 수행하지 않았다. 현재 GitHub 통합 대상은 v6.0.0이며 [업로드 기록](../../validation/test-records/v6/PUBLICATION_20261007_KO.md)에 기존 검증과 이번 재시험 생략, 10영상 잠정 결과를 구분한다.

전체 시험은 Windows CPython 3.14.7에서 **198개 통과(78.64초)**했다. 기존 dataset/preview 장벽과 통합 세션 누락 차단을 포함한다. GUI 생성/종료·실제 4영상 프로젝트 로드, CLI 도움말, pip check는 통과했다. ZIP 재계산에서 E120 212/221 경고 관측이 충돌 전후 적합에 사용됨을 확인했다. 잠정 μ_b=0.18201687, e_n=0.67513784이며 접선 계수는 적격 2사건으로 보류했다. 원 관측 재계산+계수 저장은 137.76초, 그중 계수 작업은 62.58초다. 상세 수치·남은 보류·미검증 범위는 [실행 기록](../../validation/test-records/v6/REPORT_KO.md)에 남긴다.

사용 안내는 [v6 안내](../operations/README_V6_KO.md), 분담 규약은 [통합 안내](../operations/DISTRIBUTED_ANALYSIS_V6_KO.md), 계약은 [V6_DATA_ADDITIONS_KO.md](../methods/V6_DATA_ADDITIONS_KO.md), 결정은 [ADR-008](../decisions/ADR-008-v6-warning-and-integration.md), 인수 범위는 [V6_REQUIREMENTS_KO.md](V6_REQUIREMENTS_KO.md)다. 다음은 개발에 사용하지 않은 새 촬영 세션의 독립 시간·거리 및 고정 예측 검증이다. 잠정 숫자는 참값이 아니다.

---

<!-- V5 RELEASE -->
# v5.0 현재 상태

자동 영상 구간·원/표식 계측·프레임 색인·충돌 변화점·탐색 계수 포함 기준·UI를 갱신했다. 수동 시작은 선택 경로로 남긴다. 기존 canonical 계층과 schema 2.0을 유지한다. 정확한 실행 결과는 [v5 검증 보고서](../../validation/test-records/v5/REPORT_KO.md)를 따른다.

다음 연구 검증은 개발에 사용하지 않은 영상의 독립 라벨과 독립 길이·시간 오차 검증이다. 자동 성공률을 물리 정확도로 해석하지 않는다. 과거의 Phase 2 제안보다 명시적 사용자 요청을 우선한다.

---

<!-- V45 RELEASE -->
# v4.5 현재 상태 (2026-10-01)

현재 릴리스는 4.5.0이다. 아래 v4 기준선은 이력이다. v4.5에서는 사용자 요청에 따라 시작·종료/재진입·충돌·표식 검토와 계수 작업을 함께 개선했다.

- Python 3.14.6 / Windows, `requirements-v45-tested.txt`.
- 자동 시험 142개 통과. 단축키 수명 처리·구간 경계 수정을 포함한 최종 전체 검사.
- Drive 목록과 대조한 실제 원본 49개: 모두 분석·저장 완료. 칩 수 제안은 폴더 표시와 49/49 일치. 전수 프레임 정답 검증과 다르다.
- 보정 원본 3개 새 처리. 사람이 저장한 시작점 재사용 3개에서 측정·피팅·검증 별도 실행.
- 기존 schema 2.0 + 추가 review_schema_version=1. 최상위 import 호환 경로 보존.
- [인수·검증 보고서](../../validation/test-records/v45/REPORT_KO.md), [요구사항 대응표](V45_REQUIREMENTS_KO.md), [사용법](../operations/README_V45_KO.md).
- 현재 코드베이스 통합 시 최초 분석/재분석 사건 ID 안정화와 칩 구간 범위 검증을 보완하고 회귀시험 2개를 추가했다. 빠른 통합 검사는 통과했으며 전체 pytest 재실행은 남아 있다.

다음 연구 작업은 새 영상의 독립 길이·중심·표식 기준으로 측정 오차를 평가하는 것이다. 미승인 충돌을 억지로 승인하거나 숫자가 없는 계수를 0으로 채우지 않는다. 보고된 오차/보류 이유를 기준으로 추가 영상을 설계한다.

---

# 현재 개발 상태와 다음 작업

최종 갱신: 2026-09-30

## 현재 기준선

- 저장소 버전 표기: v4.0.0, 다음 안전 패치는 아직 별도 릴리스 번호 없음
- 프로젝트 schema: 2.0
- 지원 Python: `>=3.12,<3.15`
- 실제 최신 자동 검증 환경: Windows 11, CPython 3.13.3
- 고정 의존성: `requirements-v4-tested.txt`
- 전체 자동 시험: **126 passed in 37.18s**
- 1단계 데이터 무결성 직접 시험: **10 passed**
- `pip check`, CLI help, PySide6 offscreen `MainWindow` 생성·종료: 통과

상세 실행 증거는 [1단계 검증 기록](../../validation/test-records/PHASE1_DATA_INTEGRITY_20260930_KO.md)에 있다. 자동 시험 통과는 새로운 실제 영상에서 물리계수가 독립 검증됐다는 뜻이 아니다.

## 완료된 큰 작업

### 저장소 재구성

- 원본 v4.0.0 ZIP과 전체 산출물을 `archive/releases/v4.0.0/`에 동결
- canonical 패키지를 `core/measurement/analysis/models/application/ui`로 분리
- 기존 import 경로와 실행 인터페이스에 호환 shim 유지
- 대용량 중복 결과는 활성 트리에서 제외하고 최소 증거만 유지

### Phase 1: 데이터 무결성 P0

- measurement/analysis/physics/export 단계별 코드 digest
- 영상별 correction dependency projection
- 최종 검토 사건을 사용한 운동학 장벽과 일괄 ±6프레임 제외 제거
- 중심 수정 후 중심 기준 각도·표식·품질의 stale 처리
- run 측정 스냅샷과 현재 물리 스냅샷 결합 및 provenance 기록
- 위치 기반 `e_normal`과 회전 기반 IFR 자료 분리
- IFR가 `e_normal`을 재최적화하거나 덮어쓰지 않도록 고정
- GUI job/project/settings context와 preview token 검증
- 모델 ID, 식 버전, 적용 범위 기록

## 아직 완료되지 않은 연구·개발

- Schema 3.0: 칩별 유효 구간, 채널별 품질, 안정 사건 ID, artifact dependency graph
- 사람이 접촉 전후 경계와 사용 불가 범위를 직접 편집하는 review UI
- 단일 영상 경로만으로 시작 가능한 간편 CLI와 review spec
- 그래프·표에 시간/기하/회전 상태와 단위를 더 명확히 표시
- 계수별 release gate, 세션 bootstrap, 새 독립 실제 영상 검증
- 실제 FHD240 장시간·32GB Windows 환경, DPI/키보드/긴 한국어 UX 검증
- 배포 기준 CPython 3.12에서 최신 126개 이상 시험 반복

## 다음 기본 작업: Phase 2 Schema 3.0 설계 인벤토리

사용자가 다른 우선순위를 지정하지 않으면 다음 작업은 **코드를 바로 이동하는 것이 아니라 현재 schema의 모든 writer/reader를 목록화하고 추가형 migration 시험을 먼저 설계하는 것**이다.

첫 작업 묶음:

1. `project.json`, run manifest, SQLite events/observations/trajectories, export writer와 reader 위치를 `rg`로 목록화한다.
2. schema 2.0 fixture가 손실 없이 열리는 현재 동작을 회귀시험으로 고정한다.
3. Schema 3.0 제안에 다음 최소 객체를 정의한다.
   - 칩별 유효/제외 frame interval과 이유
   - position/orientation/identity/time/geometry 채널별 품질
   - 재분석 후에도 가능한 한 대응되는 안정 event identity
   - Measurement/Derived/Physics/Validation/Presentation artifact와 dependency hash
4. 2.0→3.0 추가형 migration, round-trip, 이전 import/CLI 결과 호환의 완료 조건을 문서화한다.
5. 제안과 시험을 검토한 뒤에만 `core/migration.py`, `core/config.py`, `core/storage.py` 구현을 시작한다.

## 다음 작업에서 바꾸지 않을 것

- Farkas/IFR 지배식과 부호
- 현재 계수 값이나 동결 v4 결과
- 기존 schema 2.0 프로젝트를 여는 기능
- 기존 CLI 명령과 호환 import
- GUI 화면 재설계와 단일 영상 CLI를 Schema 3.0 첫 패치에 함께 섞는 것

## 작업 시작 전 확인

- [로드맵](ROADMAP_KO.md)의 Phase 2 완료 조건
- [아키텍처](../architecture/ARCHITECTURE_KO.md)의 호환 경계
- [데이터 사전](../methods/DATA_DICTIONARY_KO.md)의 현재 필드
- [테스트 안내](../operations/TESTING_KO.md)의 기준선 명령
- 관련 ADR과 새 결정이 필요한지 여부
