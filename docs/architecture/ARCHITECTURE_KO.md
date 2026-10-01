# 아키텍처와 데이터 흐름

## 설계 목표

하나의 과학 계산 경로를 CLI와 선택적 GUI가 공유한다. UI는 입력·검토·진행 표시를 담당하고, 관측·운동학·물리 피팅을 복제하지 않는다. 원본과 각 계산 단계의 provenance를 보존하여 설정이나 코드가 바뀌면 필요한 단계만 다시 계산한다.

## 계층

- `src/pokerchip/core/`: 프로젝트 설정, schema migration, 저장, 해시, 시간축
- `src/pokerchip/measurement/`: 영상 디코딩, 보정, 검출, 표식, 추적, 시작 구간
- `src/pokerchip/analysis/`: 운동학, 사건 정제, 품질, 독립 정답 비교
- `src/pokerchip/models/`: Farkas/IFR/simulator, 상태 환산, 피팅, 연구 workflow
- `src/pokerchip/application/`: 분석 pipeline, batch/job, 자동 workflow, export와 delivery
- `src/pokerchip/ui/`: `review_base`→`research_window`→`main_window` GUI 계층과 viewer/forms
- `src/pokerchip/*.py`, `src/pokerchip/physics/`: 한 릴리스 동안 canonical 모듈을 가리키는 호환 import

의존 방향은 대체로 `core ← measurement/analysis/models ← application ← cli/ui`다. `ui`의 값을 과학 함수가 직접 읽도록 만들지 말고, 직렬화 가능한 설정이나 명시적 인자로 전달한다.

## 진입점

- `run_cli.py`와 `pokerchip.cli`: 프로젝트 생성, 등록, 분석, 피팅, 시뮬레이션, export
- `run_gui.py`, `RUN.cmd`, `pokerchip.gui`: Windows GUI
- `scripts/reproduction/`: 동결 v4 자료 재현
- `scripts/validation/`: 검증·보고서 생성
- `scripts/benchmarks/`: 운영 성능 측정

CLI와 GUI의 동일 작업은 `application` 또는 `models`의 같은 함수를 호출해야 한다. CLI만을 위한 축약 계산이나 GUI 내부의 별도 물리 구현을 추가하지 않는다.

## 주 분석 흐름

```text
외부 원본 영상 + project/experiment 설정
  → measurement: frame timing, calibration, detections, tracking
  → analysis: manual corrections, kinematics, reviewed events, quality
  → models: free/normal/IFR trials, fit, frozen-parameter prediction
  → application: transactional run, cache, export, batch coordination
  → CLI 또는 GUI가 같은 결과를 표시
```

원본 영상은 참조만 하며 자동으로 수정하지 않는다. 각 run은 `manifest.json`, `effective_settings.json`, `experiment.json`, `records.sqlite`, export를 가진다.

## 계산 단계와 무효화

- measurement/raw: 원본 해시, 보정, 표식, 칩 기하, 검출 설정, 분석 구간
- analysis: raw, 시간축, 운동학 설정, 제외 구간, 해당 영상의 수동 수정
- physics: analysis, 칩 물성, 물리 모델, split
- export: physics, 표시 설정, 실험 표시 identity

각 단계는 canonical 소스 digest를 포함한다. UI와 호환 shim만 바뀌어도 과학 캐시가 무효화되지는 않는다. 안전을 위해 일부 공통 파일 변경은 보수적인 추가 cache miss를 만들 수 있다.

## 설정 스냅샷

관측·운동학은 run의 불변 `effective_settings.json`과 연결된다. 후속 계수 피팅은 그 측정 스냅샷을 유지하면서 현재 프로젝트에서 명시적으로 선택한 질량·관성·물리 모델을 결합한다. 두 입력의 해시는 provenance에 별도로 기록한다. 자세한 결정은 [ADR-002](../decisions/ADR-002-measurement-snapshot-current-physics.md)를 따른다.

## 사건과 운동학 장벽

자동 검색 후보 범위는 물리적 접촉 지속시간이 아니다. 최종 사건의 `contact_frame_interval` 또는 정제된 `boundary_frame_interval`과 `unusable_frame_intervals`를 장벽으로 사용한다. 제외된 비접촉 사건은 장벽이 아니다. 구형 사건에 새 필드가 없을 때만 후보 범위를 보수적으로 사용한다.

## 비동기 안전

GUI background job은 job ID, project ID, folder, 설정 해시를 캡처한다. 작업 중 프로젝트나 설정이 바뀌면 완료 결과를 현재 프로젝트에 연결하지 않는다. 프리뷰 요청은 별도 token으로 오래된 성공·실패 신호를 무시한다. 자동 workflow처럼 의도적으로 프로젝트 상태를 갱신하는 작업만 명시적 허용 플래그를 사용한다.

## 외부 호환 경계

다음은 별도 migration·호환 계획 없이 깨지지 않아야 한다.

- `project.json`과 schema version
- SQLite 테이블과 기존 레코드 의미
- 공개 CSV/JSON 필드와 단위
- 기존 `pokerchip.*` import 경로
- CLI 명령과 exit code
- `run_cli.py`, `run_gui.py`, `RUN.cmd`, `SETUP.cmd`

Schema 3.0은 기존 schema 2.0을 읽는 추가형 migration부터 구현해야 한다. 외부 필드를 제거하거나 의미를 바꾸는 작업은 독립 릴리스 결정이 필요하다.

## 결과와 보관

- 활성 결과·요약: `results/v4/`
- 실행별 검증 기록: `validation/test-records/`
- 절차: `validation/protocols/`
- 불변 원본 배포본: `archive/releases/v4.0.0/`
- 과거 설명: `docs/history/`

동결 결과 위에 새 결과를 덮어쓰지 말고 새 ID나 새 버전 디렉터리를 사용한다.
