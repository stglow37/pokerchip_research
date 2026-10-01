<!-- V45 RELEASE -->
# v4.5 인계 결과

완료 범위, 새 데이터 계약, 호환 회귀시험, 142개 테스트, 실영상 진단, GUI 실행, 개발 환경 및 남은 연구 검증 범위는 `../../validation/test-records/v45/REPORT_KO.md`와 `V45_REQUIREMENTS_KO.md`에 기록했다. 소스 ZIP에서 캐시·가상환경·실험 원본은 제외한다. 원본 사용자 프로젝트와 영상은 보존한다. 아래 일반 체크리스트는 다음 개발에도 적용한다.

---

# AI·개발자 인수인계 체크리스트

작업 종료 전에 아래 항목을 확인한다. 모두 해당하지는 않지만, 미실행 항목을 실행한 것처럼 기록하지 않는다.

## 1. 범위와 결과

- [ ] 사용자가 요청한 범위와 실제 변경 범위를 한 문단으로 설명할 수 있다.
- [ ] 의도적으로 미룬 작업과 예기치 않게 남은 작업을 구분했다.
- [ ] 관측, 파생량, 모델 예측, 독립 검증을 혼동하지 않았다.
- [ ] 물리식·단위·부호·적용 범위 변경 여부를 명시했다.

## 2. 호환성과 데이터

- [ ] `project.json`, SQLite, CSV/JSON, CLI, import 호환 영향 검토
- [ ] 기존 schema 프로젝트와 동결 결과를 수정하지 않음
- [ ] 원본 영상·외부 PDF·archive 불변성 유지
- [ ] 새 필드의 의미·단위·null/보류 조건을 데이터 사전에 반영
- [ ] cache/artifact 무효화 범위를 확인

## 3. 코드와 결정

- [ ] 과학 계산이 CLI/GUI에 중복되지 않음
- [ ] canonical 모듈을 수정하고 호환 shim을 보존
- [ ] 중요한 새 선택은 `docs/decisions/` ADR로 기록
- [ ] 관련 없는 사용자 변경을 되돌리지 않음

## 4. 검증

- [ ] 변경과 직접 관련된 시험 통과
- [ ] 전체 시험을 실행했거나 실행하지 못한 정확한 이유 기록
- [ ] Python/OS/의존성 버전 기록
- [ ] CLI와 GUI 진입점 영향이 있으면 smoke test
- [ ] 합성 결과와 실제 영상 근거를 구분
- [ ] 임시 `work/`, cache, `__pycache__` 정리 여부 확인

## 5. 문서 상태

- [ ] `CURRENT_STATE_KO.md`의 기준선과 다음 작업 갱신
- [ ] `ROADMAP_KO.md`의 완료 조건과 상태 갱신
- [ ] `CHANGELOG.md`에 사용자에게 중요한 변경 기록
- [ ] 새 문서가 `CONTEXT_INDEX_KO.md`에서 발견 가능
- [ ] 검증 증거를 `validation/test-records/`에 저장

## 6. 다음 작업 인계 형식

마지막 보고에는 다음을 포함한다.

1. 완료한 결과
2. 변경한 핵심 파일
3. 실행한 검증과 정확한 결과
4. 남은 위험과 미검증 범위
5. 다음 권장 작업 한 개
6. 다음 작업의 첫 명령 또는 첫 확인 파일

## 현재 다음 작업을 인계할 때

현재 기본 다음 작업은 Phase 2 Schema 3.0 인벤토리다. 첫 구현자가 먼저 읽을 파일은 다음과 같다.

- `docs/development/CURRENT_STATE_KO.md`
- `docs/development/ROADMAP_KO.md`
- `docs/architecture/ARCHITECTURE_KO.md`
- `docs/methods/DATA_DICTIONARY_KO.md`
- `src/pokerchip/core/config.py`
- `src/pokerchip/core/migration.py`
- `src/pokerchip/core/storage.py`

첫 산출물은 코드 패치가 아니라 현재 schema writer/reader 목록과 2.0 fixture 보존 시험 계획이어야 한다.
