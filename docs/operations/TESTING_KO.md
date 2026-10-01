<!-- V5 RELEASE -->
# v5 시험 진입점

`python -m pytest -q`가 전체 회귀시험이다. v5 최종 Windows/Python 3.14.6 시험은 167개 통과했다. `tests/regression/test_v5.py`는 새 프레임·구간·원·추적·충돌·CLI 회귀를 포함한다. 실영상은 `validation/run_v5_real.py 경로목록.json 결과폴더`로 재현한다. 개발 결과 재개 시 `--resume`는 완료 영상의 구간을 보존하고 stage fingerprint에 따라 필요한 단계를 갱신한다. 공통 파이프라인 변경은 원 관측 캐시도 무효화할 수 있다. 결과는 [v5 기록](../../validation/test-records/v5/REPORT_KO.md)을 참고한다.

---

# 테스트 환경과 검증 절차

## 지원·검증 환경

- `pyproject.toml` 지원 범위: Python 3.12 이상 3.15 미만
- 배포 문서의 기준: Python 3.12
- 최신 릴리스 자동 검증: Windows, CPython 3.14.6
- 고정 패키지: `requirements-v45-tested.txt`
- 최신 실행 증거: v4.5 배포 후보의 142 passed. 통합 후 사건 ID·구간 회귀시험 2개가 추가되어 다음 전체 실행의 예상 collection은 144개 이상이다.
- 배포 기준 CPython 3.12의 v4.5 전체 재실행은 아직 남아 있다.

Python 버전이 다르면 결과에 정확한 버전을 기록한다. 한 버전의 통과를 다른 버전에서도 실행했다는 뜻으로 쓰지 않는다.

## Windows 환경 준비

PowerShell에서 저장소 루트를 기준으로 실행한다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-v45-tested.txt
.\.venv\Scripts\python.exe -m pip check
```

3.12 launcher가 없고 지원 범위의 다른 Windows Python을 사용할 경우, 사용한 버전을 검증 기록에 남긴다. MSYS Python은 Windows wheel 대신 NumPy 소스 빌드로 전환될 수 있으므로 이 저장소의 Windows 기준 환경으로 사용하지 않는다.

## 전체 시험

일부 실행 환경은 사용자 Temp의 `pytest-of-*` 접근을 거부한다. 저장소의 git-ignored `work/`를 명시하면 이를 피할 수 있다.

```powershell
New-Item -ItemType Directory -Path work -Force | Out-Null
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m pytest -q --basetemp=work\pytest
```

현재 성공이 확인된 실행 증거는 v4.5 배포 후보의 `142 passed`다. 통합 후 첫 전체 실행에서는 새 회귀시험을 포함해 `144 passed` 이상이어야 한다. 시험 추가 후 숫자가 증가할 수 있으므로 감소했을 때는 collection 누락 여부를 확인한다.

## 단계별 빠른 검사

```powershell
# Phase 1과 이전/새 import 호환
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m pytest -q `
  tests\regression\test_phase1_integrity.py `
  tests\unit\test_module_layout.py `
  --basetemp=work\pytest-phase1

# 물리식과 사건
.\.venv\Scripts\python.exe -m pytest -q `
  tests\unit\test_physics.py tests\unit\test_events.py `
  --basetemp=work\pytest-physics

# 합성 E2E와 피팅
.\.venv\Scripts\python.exe -m pytest -q `
  tests\integration\test_operations.py tests\integration\test_study.py `
  --basetemp=work\pytest-integration
```

## 진입점 smoke test

```powershell
.\.venv\Scripts\python.exe run_cli.py --help
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'src'); from PySide6.QtWidgets import QApplication; from pokerchip.ui.main_window import MainWindow; app=QApplication.instance() or QApplication([]); w=MainWindow(); print(w.windowTitle()); w.close()"
```

`RUN.cmd`는 실제 GUI event loop를 시작하므로 자동 smoke에서는 구조와 동일 `run_gui.py` 호출을 검사하고, 사람이 Windows에서 최종 확인할 때 직접 실행한다.

## 구문 검사

의존성을 import하지 않고 모든 Python 파일을 확인할 때 사용한다.

```powershell
@'
import ast
from pathlib import Path
files = list(Path("src").rglob("*.py")) + list(Path("tests").rglob("*.py"))
for path in files:
    ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
print(f"AST_OK={len(files)}")
'@ | python -
```

## 변경 유형별 필수 검증

- schema/storage: migration, round-trip, SQLite backup, 이전 fixture
- measurement: 합성 영상 E2E, 검출/추적, 원본 불변성
- event/kinematics: 결측·장벽·불규칙 timestamp·one-sided fit
- physics: 독립 적분, 보존량, passivity, 계수 복원
- fitting: split 누출, 고정 계수, 식별성, 경계, bootstrap
- CLI/GUI: 공통 결과, background context, preview token, offscreen widget
- export/docs: 필드·단위·상태·상대 링크와 이미지 존재

## 결과 기록

의미 있는 milestone마다 `validation/test-records/`에 다음을 기록한다.

- 날짜, OS, Python과 패키지 버전
- 실행한 정확한 명령
- 통과/실패/skip 수와 실행 시간
- 실패 원인과 수정 또는 보류 근거
- 합성시험인지 실제 영상 시험인지
- 실제 물리 정확도에 대해 주장할 수 없는 범위

## 임시 산출물

`.venv/`, `work/`, `.pytest_cache/`, `__pycache__/`는 Git에 포함하지 않는다. 정리할 때 저장소 안의 정확한 경로인지 확인하고 원본 영상·동결 결과·사용자 작업을 삭제하지 않는다.
