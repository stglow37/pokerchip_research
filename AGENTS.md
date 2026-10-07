<!-- V6 IMPLEMENTATION -->
# 현재 v6.0.0 안내

v6.0.0 구현·인수 근거는 `docs/development/V6_REQUIREMENTS_KO.md`, `validation/test-records/v6/REPORT_KO.md`, 현재 사용법은 `docs/operations/README_V6_KO.md`다. Windows CPython 3.14.7에서 전체 198개 시험을 통과했다. 독립 물리 정확도는 별도 연구 과제다. 아래 이전 릴리스 원칙을 유지하며 현재 상태/로드맵의 최신 상단을 우선한다.

---

<!-- V5 RELEASE -->
# 이전 릴리스 v5.0

현재 사용법은 `docs/operations/README_V5_KO.md`, 요구사항 대응은 `docs/development/V5_REQUIREMENTS_KO.md`, 검증 증거는 `validation/test-records/v5/REPORT_KO.md`가 정본이다. 자동 구간은 사람 승인과 구분한다. 아래 v4.5/v4 내용은 계승 원칙과 과거 기록이다.

---

<!-- V45 RELEASE -->
# 현재 릴리스 안내

이 절은 v4.5.0 당시 안내다. 아래의 ‘126개 / Python 3.13 / Phase 2 다음 작업’은 v4 정리 당시 기준이다. v4.5 릴리스 기록은 142개 통과이며 통합 과정에서 사건 ID·구간 회귀시험 2개가 추가되었다. 현재 기준은 `docs/development/CURRENT_STATE_KO.md`, `docs/operations/TESTING_KO.md`, `validation/test-records/v45/REPORT_KO.md`를 따른다. 기존 원칙과 canonical 구조는 유지한다.

---

# PokerChip 연구 저장소 AI 작업 지침

이 파일은 모든 작업에 적용되는 짧은 진입점이다. 상세 사실은 링크된 정본 문서를 따른다.

## 세션 시작

1. `docs/CONTEXT_INDEX_KO.md`를 읽는다.
2. `docs/development/CURRENT_STATE_KO.md`에서 현재 완료 상태와 다음 작업을 확인한다.
3. `docs/development/ROADMAP_KO.md`에서 해당 작업의 범위·완료 조건을 확인한다.
4. 물리·필드 변경 전 `docs/methods/MODEL_DECISIONS_KO.md`와 `docs/methods/DATA_DICTIONARY_KO.md`를 읽는다.
5. 명시된 사용자 요청이 없으면 코드를 임의로 변경하지 말고 다음 권장 작업과 근거를 보고한다.

## 절대 원칙

- 관측값, 파생량, 모델 예측, 독립 검증 결과를 서로 구분한다.
- optimizer 성공이나 합성시험 통과를 실제 물리 정확도로 표현하지 않는다.
- 물리식·부호·단위·적용 범위를 바꾸려면 근거, ADR, 회귀시험을 함께 갱신한다.
- CLI와 GUI에는 과학 계산을 복제하지 않는다. 둘 다 `application` 서비스를 사용한다.
- `project.json`, SQLite, CSV/JSON, CLI, `RUN.cmd`, 기존 `pokerchip.*` import 호환성을 확인한다.
- 원본 영상, 외부 PDF, `archive/releases/` 동결본을 수정하거나 삭제하지 않는다.
- 과거 문서는 현재 사양이 아니다. `docs/history/`는 증거와 맥락으로만 읽는다.
- 기존 사용자 변경을 보존하고 관련 없는 파일을 정리하거나 되돌리지 않는다.

## 구현과 검증

- canonical 코드는 `src/pokerchip/{core,measurement,analysis,models,application,ui}`에 둔다.
- 최상위 호환 모듈은 명시적 폐기 결정 전까지 유지한다.
- 변경 전후 `docs/operations/TESTING_KO.md`의 관련 시험을 실행한다.
- v4의 과거 자동 기준선은 Windows CPython 3.13.3의 `126 passed`이며, v4.5 릴리스 기록은 CPython 3.14.6의 `142 passed`이다.
- 새 결정은 `docs/decisions/`, 새 실행 증거는 `validation/test-records/`에 남긴다.
- 작업 종료 시 `docs/development/HANDOFF_CHECKLIST_KO.md`를 따른다.

## 현재 기본 다음 작업

사용자가 다른 우선순위를 지정하지 않았다면 Phase 2의 Schema 3.0 인벤토리와 추가형 마이그레이션 시험 설계가 다음 작업이다. 구현 전에 `CURRENT_STATE_KO.md`의 시작 조건을 확인한다.
