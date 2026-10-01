# Windows 11 / VS Code 실행 매뉴얼

## 1. 설치와 첫 실행

1. 64비트 Python 3.12를 설치합니다. 검증한 환경은 CPython **3.12.14**입니다. VS Code와 Microsoft Python 확장을 준비합니다.
2. ZIP 전체를 예를 들어 `D:\PokerChipResearch`에 풉니다. ZIP 안에서 실행하거나 `.py` 한 파일만 옮기지 않습니다.
3. VS Code의 **파일 → 폴더 열기**에서 `pyproject.toml`, `run_gui.py`, `src`가 함께 보이는 폴더를 엽니다.
4. **터미널 → 새 터미널**을 열어 PowerShell에서 `Get-Location`으로 현재 폴더를 확인합니다.
5. 아래 명령을 한 줄씩 실행합니다. 경로에 공백이 있다면 인수를 큰따옴표로 감쌉니다.

```powershell
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps --no-build-isolation
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe run_cli.py --help
.\.venv\Scripts\python.exe run_gui.py
```

6. `Ctrl+Shift+P` → **Python: Select Interpreter** → 이 폴더의 `.venv\Scripts\python.exe`를 선택합니다. VS Code 편집기 인터프리터와 터미널 Python이 다를 수 있습니다.
7. GUI 상단 **합성 데모 만들기**를 누르고 빈 폴더를 선택합니다. **모두 분석 / 재개**로 분석합니다. 작업 행을 더블클릭하여 영상·그래프를 봅니다.

기존 데모 폴더는 다시 생성하지 말고 **프로젝트 열기**에서 `project.json`을 선택하세요. 이 프로그램은 실행 정책 변경이나 관리자 권한을 요구하지 않습니다.

## 2. GUI 사용 순서

상단 **새 프로젝트**는 데이터 저장용 빈 폴더를 만듭니다. 프로그램 소스 폴더와 실험 데이터 폴더를 구별하세요. 한 프로젝트 안에서 영상 조건의 `session_id`를 달리 설정해 여러 촬영 세션을 묶을 수 있습니다.

### 1 · 영상 등록 / 작업

- **영상 여러 개 등록** 또는 파일 끌어놓기로 등록합니다. 50개 이상 등록 가능하며 실제 영상은 작업 순서에 따라 하나씩 읽습니다. 기본 참여 칩은 3개이므로 단일/2칩 영상은 반드시 수정합니다.
- 여러 행 선택 → **선택 조건 수정**에서 `session_id`, `participating_chip_ids`, `interval`, `conditions`, `excluded_frame_intervals`를 함께 적용합니다. 개별 행만 선택하면 예외를 수정할 수 있습니다. `interval: [0,null]`은 끝까지이며 숫자는 decoded frame index입니다.
- `participating_chip_ids`는 화면에 우연히 보이는 모든 칩이 아니라 실험 참여 칩입니다. 배경 여분 칩은 `analysis.roi_px`와 분석 구간으로 배제합니다. 자동 `chip_count_proposal`은 검토용 제안입니다.
- 보정 영상은 **끌어놓기: ChArUco 보정 영상**으로 바꿔 넣습니다. 보정 모드에서는 첫 파일 1개를 사용합니다. 보드 실측 길이와 촬영 모드를 입력해야 실행합니다.
- **일시정지 / 계속 / 취소**는 프레임 또는 분석 단계의 안전 지점에서 반영됩니다. 진행 중 창 닫기는 취소 저장을 먼저 요청합니다. 피팅·보정 작업은 완료 후 창을 닫습니다.
- 실패 행을 선택해 **선택 분석 / 재시도**를 누릅니다. 취소·강제 종료 후에도 **모두 분석 / 재개**가 마지막 완전 checkpoint를 사용합니다. 복구 시 원본 앞부분을 다시 디코딩하여 건너뛸 수 있어 즉시 시작되지 않을 수 있습니다.

### 2 · 시간 / 보정 / 표식

설정은 JSON 편집기로 명확히 노출합니다. `null`은 미측정이며 0이 아닙니다. **적용·저장**을 눌러야 반영됩니다. JSON 불러오기는 편집기에만 넣으므로 검토 후 적용합니다. 사용 가능한 예시는 `examples/`에 있습니다.

1. **칩 실측 규격**: 각 ID의 반지름·질량·두께를 SI로 입력합니다. 관성 실측이 없다면 `inertia_model: "uniform_disk"`를 본인이 명시적으로 선택할 수 있습니다. 명목 지름 40mm를 실측했다고 바꾸지 않습니다.
2. **시간 PTS 검사**로 `intake/실험ID/metadata.json`, `timing.csv`를 만듭니다. 독립 시간 근거를 확인한 뒤 time profile의 `status: "verified"`, `evidence`, `segments`를 입력합니다. 재생 fps만 보고 240 또는 factor 8을 입력하지 마세요.
3. **ChArUco 영상 보정**에서 보드 사양과 모드를 입력합니다. 선명도·코너 수·위치/크기 차이로 pose를 선별하고 heldout pose의 별도 점으로 오차를 검사합니다. 정지 바둑판 하나로 intrinsic 전체를 검증했다고 볼 수 없습니다.
4. 실험 영상을 검토 탭에서 연 뒤 **현재 프레임 격자 검출** 또는 **격자 대응점 클릭**으로 pixel/world 점을 만듭니다. **격자 대응점 → 평면 보정**에서 학습에 쓰지 않은 `holdout`과 독립 길이를 입력합니다. 대응 좌표의 y축은 위쪽을 양수로 정합니다.
5. 보정 profile의 영상 표시 크기와 `capture_mode`가 실험 영상 조건과 일치해야 합니다. 필요하면 개별 experiment에 `time_profile`, `calibration`, `analysis`, `templates` 전체 블록을 넣어 별도 profile을 사용합니다. 파일이 같은 카메라라는 이유만으로 줌/안정화/slow모드 차이를 무시하지 않습니다.
6. **계측·회전 alias 상한**에서 대략적인 칩 픽셀 반경, ROI, `omega_bound_rad_s`를 입력합니다. 속도 상한은 독립 근거가 있어야 합니다. 상한이 없으면 방향 각도는 보여도 각속도는 비활성화됩니다.

### 3 · 영상 / 사건 검토

- 작업 행을 열고 슬라이더를 움직입니다. 표시 영상은 원본 프레임에 관측 중심/반경을 겹친 것입니다. 그래프 붉은 세로선과 사건 표가 같은 frame index에 연결됩니다. 그래프 선택으로 거리·선명도도 봅니다.
- **선명한 표식 기준 프레임 제안**은 선명도 기반 후보를 보여줍니다. 가림 없는 두 표식과 칩 ID는 사람이 확인합니다. ID를 선택하고 `rim 표식 클릭`, `inner 표식 클릭`으로 각각 중심을 누른 뒤 **표식 학습 저장**을 누릅니다. 서로 다른 선명한 프레임을 반복해 3회 이상 학습하는 편이 좋습니다. 프레임을 바꾸면 미저장 클릭은 지워집니다.
- unknown 칩에는 고정 ID를 임의로 주지 않습니다. 실제 표식을 보고 **ID 구간 교환**에서 ID 변경/교환 범위를 지정합니다. `set_id` 기능도 이 대화상자에서 사용합니다.
- **중심 보정 클릭**, **경계 호 재적합**, **각도 보정**은 수정 이유를 요구합니다. 원시 관측을 삭제하지 않고 수정 이력을 기록합니다. **실행 취소 / 다시 실행**은 수정 이력 cursor를 변경합니다.
- 수정 뒤 **보정 반영 재분석**을 눌러 새 run을 생성하고 결과를 다시 엽니다. 저장만으로 기존 run 숫자가 바뀌지는 않습니다.
- 사건 표를 선택하면 사건 프레임으로 이동합니다. 전후 상태와 접촉을 확인하고 **사건 승인** 또는 **사건 제외 / 종류**로 처리합니다. 동시 다체·지속 접촉·뜀/쌓임은 기본 IFR 피팅에 넣지 않습니다.

### 4 · 피팅 / 예측 비교

1. 프로필의 **학습 / 보류 세션**에 train과 holdout을 분리합니다. 같은 영상의 프레임 일부를 보류로 쪼개지 않습니다.
2. 현재 run에서 충돌/발사/결측 없는 자유운동 구간을 선택하고 **현재 run → 피팅 데이터 추가**에서 `kind: "free"`와 시작/끝을 입력합니다. 여러 단일칩 실험을 모읍니다.
3. 승인된 고립 충돌은 같은 메뉴에서 `kind: "impact"`로 추가합니다. 실제 질량/관성/반지름과 시간/기하가 필요합니다.
4. **단계별 피팅 실행**은 공통 μ_b와 trial 초기 상태, e_n, e_t/μ_c를 순차 추정합니다. 결과에서 `optimizer_success`, `physical_status`, `identifiability`를 각각 봅니다. 미식별 성공을 확정 계수로 적용할 수 없습니다.
5. bootstrap은 trial/session 단위입니다. 4회는 실행 점검용입니다. 연구에서는 충분한 독립 반복 수를 확보하고 수백 회 이상에서 구간의 안정성을 확인하세요. 원본 표본이 적으면 횟수만 늘려도 해결되지 않습니다.
6. `free_motion`, `impact_conditional`, `full_forward`를 구별합니다. 완전 전방 비교는 첫 공통 관측 상태에서 한 번 시작한 뒤 관측으로 매번 재초기화하지 않습니다. 미지원 다체접촉에서는 중단 사유를 남깁니다.

### 5 · 결과 내보내기

완료 run에는 CSV/JSONL/JSON, `summary.xlsx`, `trajectories.png`, `REPORT_KO.md`가 자동 생성됩니다. **검토 overlay MP4 생성**은 원본을 다시 읽어 `overlay.mp4`와 원본 PTS 대응표를 만듭니다. **전체 완료 run 통합 Excel**은 영상별 요약입니다. 원시 궤적 전체는 CSV/JSONL로 사용하세요. 저장된 수동 보정은 재분석 후 출력에 반영됩니다.

## 3. CLI 예시

```powershell
.\.venv\Scripts\python.exe run_cli.py init "work\실험 1"
.\.venv\Scripts\python.exe run_cli.py add "work\실험 1" "D:\영상\단일 칩.mp4" --chips chip_1
.\.venv\Scripts\python.exe run_cli.py inspect "D:\영상\단일 칩.mp4" --output "work\PTS검사"
.\.venv\Scripts\python.exe run_cli.py analyze "work\실험 1"
.\.venv\Scripts\python.exe run_cli.py gui "work\실험 1"
.\.venv\Scripts\python.exe run_cli.py calibrate "D:\영상\보드.mp4" examples\charuco_board.pending.json "work\camera.json" --mode "FHD_native240"
.\.venv\Scripts\python.exe run_cli.py simulate "work\합성 데모\simulation.synthetic.json" "work\simulation.json"
```

`calibrate`의 pending 예제는 실측 길이를 채우기 전 실패하도록 되어 있습니다. `export RUN폴더 --overlay-source 원본파일`, `relink 프로젝트폴더 experiment_id 새원본경로`도 지원합니다. 명령별 `--help`로 정확한 인수를 확인하세요.

## 4. 오류 해결

| 증상 | 조치 |
|---|---|
| py/Python을 못 찾음 | 64비트 Python 3.12 launcher를 설치하거나 설치된 Python의 전체 경로로 venv 생성 |
| ModuleNotFoundError | 이 프로젝트 `.venv` Python인지 확인하고 lock 설치 후 `pip install -e . --no-deps --no-build-isolation` 재실행 |
| OpenCV 충돌/aruco 없음 | 새 venv 권장. opencv-python/headless를 중복 설치하지 않고 lock의 opencv-contrib-python 한 종류만 설치 |
| Qt plugin/display 오류 | 일반 로컬 Windows 데스크톱에서 실행. 테스트에서 설정한 `QT_QPA_PLATFORM=offscreen`은 일반 실행 시 제거. 별도 Qt/Python 경로 혼합 확인 |
| 영상 codec/회전 문제 | `inspect` 확인. 원본 회전 메타데이터를 적용하므로 ROI는 표시 좌표 기준. 손상 영상은 해당 행만 실패. 변환본은 원본과 별도로 등록하고 시간 검증 다시 수행 |
| 한글/공백 경로 | 경로를 따옴표로 감싸고 UTF-8 JSON 사용. 콘솔 문자 오류는 `python -X utf8` 사용 |
| 권한/디스크 부족 | 쓰기 가능한 데이터 폴더와 여유 공간 확보. 불완전 run을 완성으로 취급하지 않음. 원본 보존 후 재시도 |
| 속도/각속도가 빈칸 | 시간·기하 검증, alias 상한, 연속 표본, 사건 경계/가림 상태 확인. 숫자를 억지 입력하지 않음 |
| 보정 호환성 실패 | 해상도·회전·촬영 모드/줌을 맞춘 별도 calibration 사용 |
| 표식 학습 실패 | 확대해 실제 채도 있는 픽셀 중심 클릭, 동일 프레임의 두 표식, 선택 ID·조명·radial band 확인 |
| unknown/ID 모호 | 2표식과 참여 칩을 확인. 재등장 때 시간 예측만으로 확정하지 않음. 수정 이유와 구간 기록 |
| 피팅 비식별 | 서로 다른 속도/접선 조건과 독립 반복 추가. sticking-only μ_c는 하한만 결정 가능 |
| multi-contact unsupported | 해당 구간 제외 또는 별도 다체 연구 모델 필요. 쌍별 순서를 임의 지정하지 않음 |
| RAM 부족 | 기본 단일 worker 유지, 분석 구간/ROI 분할, 허용 frame byte 상한 검토. 전체 영상 프레임은 RAM에 쌓지 않음 |
| 원본 이동 | GUI 원본 재연결, 기존 SHA-256과 다르면 거부. 다른 영상으로 몰래 교체하지 않음 |
| 강제 종료 후 재개 | project.json 열기→분석/재개. 마지막 완료 chunk 이후를 재처리. 원본/설정 변경 시 새 캐시 사용 |

## 5. 재현 검사

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tools\benchmark_queue.py "work\batch52"
.\.venv\Scripts\python.exe tools\validate_extended.py "work\extended" --frames 2000
```

검증 화면은 [실제 GUI 자동검사 캡처](../../results/v4/evidence/v4_gui_range.png)에서 확인할 수 있습니다. 자동 QTest 조작 결과이며 사람이 직접 한 전체 수동 smoke test라고 주장하지 않습니다.
