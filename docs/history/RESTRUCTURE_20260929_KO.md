# 2026-09-29 저장소 재구성 감사 기록

## 범위

물리식, 분석 결과, 프로젝트/SQLite/CSV/JSON 스키마와 외부 실행 인터페이스는 변경하지 않고 v4.0.0 배포본을 연구 저장소 구조로 재배치했다.

## 보존과 제거

- 정리 시작 전에 이 작업에서 생성했던 `.cursor/`와 `tmp/`만 삭제하고, 루트가 `PokerChip_Astra_v4/`, `PokerChip_Astra_v4.zip`, `PokerChip_Astra_v4_Report.html` 세 항목과 일치함을 확인했다.
- 원본 ZIP은 `archive/releases/v4.0.0/PokerChip_Astra_v4.zip`으로 이동했으며 SHA-256과 1,317개 항목을 확인했다. 상세 값은 같은 폴더의 `MANIFEST.json`에 있다.
- 추출본의 `baseline/`, `v4/`, `controlled_v35/`, `retries/` 전체와 보고서가 직접 참조하지 않는 대용량 검증 산출물은 활성 트리에서만 제외했다. 모두 동결 ZIP 안에 남아 있다.
- 같은 SHA-256을 가진 두 HTML 보고서 중 한 부만 `results/v4/reports/`에 유지했다.
- 중첩된 `PokerChip_Astra_v4/pokerchip_research` 포장 디렉터리는 루트로 평탄화한 뒤 제거했다.

## 주요 경로 매핑

- 패키지: `src/pokerchip/` 아래를 `core`, `measurement`, `analysis`, `models`, `application`, `ui`로 분리했다.
- 이전 최상위 Python 모듈에는 한 릴리스 동안 새 모듈을 가리키는 호환 import를 남겼다.
- 누적 버전 테스트는 `tests/regression/`, 단위·통합 테스트는 각각 `tests/unit/`, `tests/integration/`으로 이동했다.
- 전체 검증 요약은 `results/v4/summaries/`, 보고서 직접 증거는 `results/v4/evidence/`, 검증 기록과 절차는 `validation/`에 배치했다.
- 실행·방법·과거 문서는 각각 `docs/operations/`, `docs/methods/`, `docs/history/`로 분류했다.

## 검증 기록

- 재구성 전 기준선: 104개 테스트 통과.
- 재구성 후: 기존 104개와 모듈 호환성 검사 12개를 합한 116개 테스트 통과.
- `run_cli.py --help`, 세 Farkas 재현 스크립트와 보고서 생성기의 `--help`를 실행했다.
- Windows/PySide6 offscreen에서 `run_gui.py` import와 `MainWindow` 생성·종료를 확인했다. `RUN.cmd`는 같은 `run_gui.py`를 루트의 `.venv`로 호출하는 구조를 검사했다.
- 합성 영상 end-to-end 분석·내보내기·캐시 검사를 별도 실행해 통과했다.
- 이전 모듈 경로와 새 모듈 경로가 같은 공개 모듈·객체를 제공함을 자동 검사했다.
- Markdown 보고서의 이미지 링크 5개가 모두 존재하고, HTML 보고서의 이미지는 자체 포함됨을 확인했다.
- 활성 요약·증거 18개가 동결 ZIP 안의 대응 파일과 SHA-256 기준으로 모두 일치했다.
- 원본 ZIP SHA-256 `e8743e150e651fccc0864e77f4c373b6134baa5a79bdec286d52e654bcac88d5`와 항목 수 1,317개를 재확인했다.
