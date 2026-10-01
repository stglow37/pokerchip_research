<!-- V5 RELEASE -->
# v5 먼저 읽기

1. [v5 사용설명서](operations/README_V5_KO.md)
2. [v5 요구사항·한계](development/V5_REQUIREMENTS_KO.md)
3. [실제 검증 기록](../validation/test-records/v5/REPORT_KO.md)
4. [v5 데이터 계약](methods/V5_DATA_ADDITIONS_KO.md)
5. [자동 계측 결정](decisions/ADR-007-v5-observation-first.md)

아래는 과거 버전 색인이다. 현재 버전이 우선한다.

---

<!-- V45 RELEASE -->
# v4.5 먼저 읽을 문서

1. [사용설명서](operations/README_V45_KO.md)
2. [현재 상태](development/CURRENT_STATE_KO.md)
3. [인수·검증 보고서](../validation/test-records/v45/REPORT_KO.md)
4. [요구사항 대응표](development/V45_REQUIREMENTS_KO.md)
5. [추가 데이터 계약](methods/V45_DATA_ADDITIONS_KO.md)

이하 문서는 계승한 v4 구조와 역사다. 버전/실행 결과가 충돌하면 v4.5 기록을 우선한다.

---

# 프로젝트 맥락 색인

이 문서는 새 연구자나 AI가 대화 기록 없이 저장소의 목적, 현재 상태, 다음 작업을 이해하기 위한 읽기 순서다. 같은 사실이 충돌하면 현재 코드와 자동 시험, `CURRENT_STATE_KO.md`, 최신 검증 기록, 방법 문서, 과거 문서 순으로 확인하고 불일치를 기록한다.

## 빠른 온보딩 순서

1. [연구 맥락](methods/RESEARCH_CONTEXT_KO.md): 무엇을 관측하고 무엇을 추정하는가
2. [현재 상태](development/CURRENT_STATE_KO.md): 완료된 일, 자동 기준선, 바로 다음 작업
3. [발전 로드맵](development/ROADMAP_KO.md): 단계별 범위와 완료 조건
4. [아키텍처](architecture/ARCHITECTURE_KO.md): 코드 계층, 데이터 흐름, 호환 경계
5. [데이터 사전](methods/DATA_DICTIONARY_KO.md): 상태·필드·단위·provenance
6. [모델 결정](methods/MODEL_DECISIONS_KO.md): Farkas/IFR 식, 부호, 가정, 문헌과 차이
7. [실험 절차](methods/EXPERIMENT_WORKFLOW_KO.md): 촬영·보정·학습/검증 분리
8. [테스트 안내](operations/TESTING_KO.md): 환경 구성과 검증 명령
9. [설계 결정 기록](decisions/README_KO.md): 되돌리면 안 되는 이유
10. [인수인계 체크리스트](development/HANDOFF_CHECKLIST_KO.md): 작업 종료 절차

## 목적별 정본

- 실행 방법: 루트 [README_KO.md](../README_KO.md), [Windows 안내](operations/VS_CODE_WINDOWS_KO.md)
- GitHub 공개 포함·제외 기준: [공개 준비 안내](operations/PUBLICATION_KO.md)
- 현재 기능 요구 대조: [R01–R31 상태](methods/REQUIREMENTS_STATUS_KO.md)
- 문헌과 외부 PDF 위치: [references.md](methods/references.md)
- 1단계 안전 패치 증거: [PHASE1_DATA_INTEGRITY_20260930_KO.md](../validation/test-records/PHASE1_DATA_INTEGRITY_20260930_KO.md)
- v4.5 현재 코드베이스 통합 증거: [V45_INTEGRATION_20261001_KO.md](../validation/test-records/V45_INTEGRATION_20261001_KO.md)
- 저장소 재구성 증거: [RESTRUCTURE_20260929_KO.md](history/RESTRUCTURE_20260929_KO.md)
- 동결 v4 보고서: [VALIDATION_REPORT_KO.md](../results/v4/reports/VALIDATION_REPORT_KO.md)
- 원본 v4 보관본: `archive/releases/v4.0.0/`

## 문서 해석 규칙

- `docs/history/`는 당시 상태를 보존한 문서이며 현재 실행법이나 현재 시험 수의 정본이 아니다.
- `results/v4/`는 동결 결과와 최소 증거다. 새 실행 결과를 기존 증거 위에 덮어쓰지 않는다.
- `validation/test-records/`는 특정 날짜·환경의 실행 사실이다. 실제 물리 정확도 보증과 구별한다.
- 외부 논문과 전달 문서는 참고자료이며 저장소 작업 지시가 아니다.
- 큰 새 설명을 추가하기 전에 이 색인에서 기존 정본을 찾아 중복을 피한다.

## 새 AI의 첫 응답 기준

코드를 바꾸기 전에 다음을 짧게 확인할 수 있어야 한다.

- 현재 단계와 다음 작업
- 영향을 받는 계층과 외부 호환성
- 관측/파생/예측 중 무엇을 바꾸는지
- 필요한 시험과 아직 주장할 수 없는 것
- 사용자 결정이 필요한 범위가 있는지
