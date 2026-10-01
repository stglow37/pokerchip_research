# PokerChip Astra v4.5

**현재 사용법은 [v4.5 한국어 사용설명서](docs/operations/README_V45_KO.md), 변경 사항과 시험 범위는 [v4.5 인수·검증 보고서](validation/test-records/v45/REPORT_KO.md)를 보세요.**

검정 칩·가장자리 색 표시·안쪽 스티커를 사용하는 연구용 프로그램입니다. 사람이 시작 장면을 확인한 뒤 자동 분석하고, 충돌 전후·표식·화면 이탈을 검토합니다. 측정 완료와 실제 정확도 검증을 구별합니다.

이 노트북에 설치한 사본은 `RUN.cmd`로 실행합니다. 다른 PC는 Python 3.14에서 `SETUP.cmd`를 먼저 실행하세요. `requirements-v45-tested.txt`는 이 버전을 검사한 환경입니다. 독립 EXE 배포본은 아닙니다.

아래의 원본 v4 구조 소개는 계승한 기능 설명입니다. 과거 테스트 결과는 v4.5 시험과 혼동하지 마세요.

포커칩의 영상 궤적을 계측하고, 자유운동 마찰과 두 원판 충돌 전후 운동을 분석하기 위한 연구용 Python 패키지다. 원본 v4.0.0 배포본과 전체 검증 산출물은 동결 보관하고, 루트에는 현재 코드와 연구 판단에 필요한 최소 증거만 유지한다.

새 연구자나 AI는 먼저 [AGENTS.md](AGENTS.md)와 [프로젝트 맥락 색인](docs/CONTEXT_INDEX_KO.md)을 읽는다. 현재 완료 상태와 바로 다음 권장 작업은 [CURRENT_STATE_KO.md](docs/development/CURRENT_STATE_KO.md)에 있다.

## 현재 지원 기능

- ChArUco 기반 렌즈·바닥 보정과 영상 시간축 설정
- 색 표식 및 무표식 원판 검출·추적, 시작/종료 프레임 제한
- 속도·각속도·사건·품질 구간 계산과 SQLite 캐시
- Farkas 분포 마찰, IFR 충돌, 파라미터 피팅 및 시뮬레이션
- GUI 검토·내보내기, CLI 일괄 분석, CSV/JSON 결과 생성
- 기존 `pokerchip.*` import, CLI 명령, `project.json`, SQLite 및 결과 필드 호환

## 설치와 실행

Windows Python 3.14 검증 환경에서 다음 진입점을 사용한다.

```bat
SETUP.cmd
RUN.cmd
```

개발 환경에서는 다음과 같이 실행할 수 있다.

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-lock.txt
.venv\Scripts\python run_gui.py
.venv\Scripts\python run_cli.py --help
```

보정 영상을 먼저 선택하고 보정판이 실험 바닥에 놓인 프레임인지 확인한다. 실험 영상을 추가한 뒤 칩 개수와 분석 범위를 검토하고, 결과의 확인 프레임과 추적 표시 영상을 원본과 대조한다. 자세한 Windows 안내는 [docs/operations/VS_CODE_WINDOWS_KO.md](docs/operations/VS_CODE_WINDOWS_KO.md), v4 사용법은 [docs/operations/README_V4_KO.md](docs/operations/README_V4_KO.md)에 있다.

## 잠정 물리 가정

전체 녹화에는 발사 전 손 접촉, 화면 이탈, 재접촉이 포함될 수 있다. 전체 녹화 시험은 소프트웨어 진단이며 자유운동 승인 자료가 아니므로 물리 계수를 계산할 때 유효 구간을 다시 확인해야 한다.

거리와 시간은 잠정값이다. 기본 격자 22.5 mm / 23.8889 mm, 칩 지름 40 mm, 질량 12 g, 균질 원판 관성, 재생시간÷8을 가정한다. 렌즈 보정 잔차·관측 비율·모델 적합 오차는 독립적인 절대 정확도와 다르다. 상세 결정은 [docs/methods/MODEL_DECISIONS_KO.md](docs/methods/MODEL_DECISIONS_KO.md), 문헌과 구현 차이는 [docs/methods/references.md](docs/methods/references.md)를 참조한다.

## 재현과 검증

```bat
.venv\Scripts\python -m pytest
.venv\Scripts\python scripts\reproduction\fit_v4.py --help
.venv\Scripts\python scripts\reproduction\holdout_v4.py --help
.venv\Scripts\python scripts\validation\make_report.py --help
```

재현 스크립트는 원본 실행 디렉터리를 묵시적으로 가정하지 않으며 입력·출력 경로를 명시적으로 받는다. 실험 절차는 [docs/methods/EXPERIMENT_WORKFLOW_KO.md](docs/methods/EXPERIMENT_WORKFLOW_KO.md), 데이터 필드는 [docs/methods/DATA_DICTIONARY_KO.md](docs/methods/DATA_DICTIONARY_KO.md)에 정리돼 있다.

## 동결 v4 증거

- 원본 배포·전체 산출물 ZIP은 로컬 동결본으로 보존하며 Git 이력에서는 제외한다. 공개가 필요하면 GitHub Release 자산으로 별도 배포한다.
- 해시·항목 수·코드 식별자: `archive/releases/v4.0.0/MANIFEST.json`
- 검증 보고서: [results/v4/reports/VALIDATION_REPORT_KO.md](results/v4/reports/VALIDATION_REPORT_KO.md)
- 활성 요약: `results/v4/summaries/`
- 보고서 직접 인용 증거: `results/v4/evidence/`
- 재구성 감사 기록: [docs/history/RESTRUCTURE_20260929_KO.md](docs/history/RESTRUCTURE_20260929_KO.md)

기존 v3.5 환경은 덮어쓰지 않는 편이 안전하다. 이전 프로젝트는 계속 열 수 있지만 설정·코드가 달라진 결과는 재분석 대상으로 표시된다.

GitHub 공개 전 포함·제외 기준과 아직 결정되지 않은 프로젝트 라이선스는 [공개 준비 안내](docs/operations/PUBLICATION_KO.md)를 확인한다.
