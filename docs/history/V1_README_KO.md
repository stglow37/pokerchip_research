# 포커칩 연구실 1.0.0

Windows용 수정 가능한 Python 연구 프로젝트입니다. 영상에서 얻은 관측과 Farkas/IFR 물리 예측을 분리하며, GUI와 CLI가 같은 분석 엔진을 사용합니다. Python 3.12.14 / Windows 11에서 실행 검증했습니다. GPU와 EXE 빌드는 필요하지 않습니다.

**프로그램 실행 검증과 실제 계측 정확도 검증은 다릅니다.** 실제 FHD native 240fps·새 3칩 표식·독립 시간/길이 기준에 대한 검증은 `pending_real_data`입니다. 제공된 과거 영상 두 개는 새 표식이 없고 시간/기하가 미확정이므로 프레임 기반 관측만 출력했습니다. 미확정 질량·관성·시간을 임의로 채우지 않습니다.

## 시작

ZIP 전체를 풀고 이 파일과 `pyproject.toml`이 있는 폴더에서 PowerShell을 여세요.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps --no-build-isolation
.\.venv\Scripts\python.exe run_gui.py
```

가상환경 활성화나 PowerShell 실행 정책 변경은 필요하지 않습니다. 최초 설치에는 인터넷이 필요합니다. 단계별 화면·오류 해결은 [Windows/VS Code 매뉴얼](../operations/VS_CODE_WINDOWS_KO.md)에 있습니다.

```powershell
.\.venv\Scripts\python.exe run_cli.py --help
.\.venv\Scripts\python.exe run_cli.py demo "work\합성 데모" --frames 90
.\.venv\Scripts\python.exe run_cli.py analyze "work\합성 데모"
.\.venv\Scripts\python.exe run_cli.py fit "work\합성 데모\fit_dataset.synthetic.json" "work\합성 피팅" --bootstrap 4
.\.venv\Scripts\python.exe -m pytest -q
```

데모 폴더는 새 폴더여야 합니다. 합성 피팅의 bootstrap 4회는 기능 점검용이며 신뢰구간 연구 결과가 아닙니다. 합성 영상의 움직임도 물리 모델 검증용 독립 궤적과 구분합니다.

## 포함 기능

- 3칩 두 색 표식 ID, 경계의 subpixel 계측, 원근/높이 보정, 가림·모호성 상태, 원시 관측과 추적 예측 분리.
- 원본 PTS와 물리 시간 분리, 구간별 slow factor, 미검증 물리 계산 차단.
- ChArUco·평면 격자 보정, 수동 대응점, 표식 색/상대각 학습, 수정 이력과 undo/redo.
- 사건 전후 분리 운동학, 고립 2체 충돌 승인, Farkas 자유운동 및 명시된 두 IFR 분기.
- 공통 계수 단계별 피팅, 초기 상태 분리, holdout·bootstrap·식별성·물리 타당성 검사.
- 단일 worker 배치, 중단 복구, 단계별 캐시, CSV/JSONL/JSON/XLSX/그래프/검토 MP4/한국어 보고서.

## 문서와 결과

| 문서 | 용도 |
|---|---|
| [VS Code 매뉴얼](../operations/VS_CODE_WINDOWS_KO.md) | 설치·GUI·CLI·오류 해결 |
| [실험 절차](../methods/EXPERIMENT_WORKFLOW_KO.md) | 촬영·시간·카메라·물성·표식·반복 실험 |
| [데이터 사전](../methods/DATA_DICTIONARY_KO.md) | 단위·상태·설정·파일 관계 |
| [모델 결정](../methods/MODEL_DECISIONS_KO.md) | 수학식·논문 불일치·적용 한계 |
| [검증 보고](VALIDATION_REPORT_KO.md) | 실제 수행 결과와 미검증 항목 |
| [R01–R31 대조표](../methods/REQUIREMENTS_STATUS_KO.md) | 구현·검사·제약 추적 |
| [의존성 안내](../../THIRD_PARTY_NOTICES.md) | 배포 구성과 라이선스 확인 위치 |

분석 출력은 연구 데이터 폴더의 `runs/run_*/export/`에 저장됩니다. `project.json`은 설정과 원본 경로를, 각 run은 당시 설정·원본 hash·수정 이력·코드 hash를 보존합니다. 원본을 이동했다면 **원본 재연결**을 사용하세요. 이전 결과는 새 결과로 덮어쓰지 않습니다.

`examples/`에는 미측정값을 null로 둔 설정과 합성 피팅 예제가 있습니다. `validation/`의 JSON·JUnit·스크린샷은 실행 증거이며 실험 원본은 포함하지 않습니다. 논문 PDF·사용자 원본 영상·가상환경은 배포 ZIP에서 제외했습니다.
