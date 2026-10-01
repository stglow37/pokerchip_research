# v2 변경 사항과 완료 범위

## 확정 실험 조건

2026-09-28 사용자 추가 지시를 반영해 **검정 칩만** 지원합니다. 가장자리 한 곳을 색칠하고 내부에 스티커를 붙이는 두 표식 구조입니다. 개선보고서의 컬러 칩 detector 제안은 이번 구현에서 철회했습니다. 색상 표식 추적은 유지합니다.

시간 기본값은 삼성 FHD 240 fps, 전체 1/8배속입니다. 재생 8초를 실제 1초로 환산합니다. 기존 프로젝트는 원래 시간 설정을 보존하며, 배속이 다른 영상에 8을 강제하지 않습니다.

## 구현 완료

| 분야 | 변경 |
|---|---|
| 화면 | 대시보드, 왼쪽 작업 순서, 설정 폼, 고급 JSON 접기, 한국어 도움말 |
| 상태 | 완료·잠정·미검증 구분, 설정 변경 후 오래된 run 표시 |
| 검토 | 다음/이전 문제, 휠 확대, 가운데 드래그, 누락 관측 입력, 기존 ID/각도/사건 correction |
| 정답 | 자동값을 미리 채우지 않는 원본 라벨 창, 완전 프레임 평가, source hash 일치, 정답 잠금 |
| 지표 | recall, precision, false positive/frame, 중심 RMSE, 각도 MAE, 라벨 프레임 사이 ID switch |
| 보정 | 독립 좌표·길이·intrinsic 오차의 수치 gate. 근거 문자열만으로 합격 불가 |
| 시간 | factor8 기본값, declared 잠정 운동학, 독립 clock 검증, exposure end, 프레임 간격 검사 |
| 추적 | 전체 Hungarian 대안 배정 비용 비교, unmatched 선택지, 모호한 ID의 trusted track 갱신 방지 |
| 관측 | 검정 면 대비/밝기 검사, 원본 subpixel 원 피팅, 후보 거절 이유 기록 |
| 사건 | 모호 ID 제외, 연속 한쪽 표본만 사용, 물리시간 창 제한, 회전 alias 변화 검사 |
| 물리 | Farkas/통합 solver 비유한 입력·계수 검사, IFR 마찰 포화 분기 설명과 여유값 |
| 피팅 | 최적 latent pre-state로 최종 IFR 진단 재계산, 법선 정규화, 양수 sigma 검증 |
| 오차모형 | 프레임별 sigma, 선택적 관측 내 공분산 whitening, 공통 scale/clock session bootstrap |
| 진단 | 계수/CI/물리허용/국소식별 분리, 보류 RMSE 표, EIV nuisance 재최적화 profile |
| 통계 | locked test와 학습/보류 중복 차단, 조건부 공분산·coverage 한계 명시 |
| 운영 | v1→v2 설정 migration·원본 백업, 취소 상태 전달, 검사 전용 tmp 경로 사용 |
| 생성기 | supersampling의 pixel-center 변환을 수정해 인위적 정답 좌표 편향 제거 |

## 유지한 v1 자산

Farkas 독립 면적적분 검사, IFR signed impulse와 보존량 검사, 연속 자유운동/이벤트 jump 통합, raw/manual/prediction 분리, 원본 hash, 코드·설정·run 연결, SQLite 저장, 단일 worker, checkpoint와 cache, CSV/JSONL/XLSX/overlay, undo/redo를 유지했습니다. `legacy_gui.py`는 검토 명령과 worker 연결을 재사용하는 기반 클래스이고 기본 실행 화면은 새 `gui.py`입니다.

## 개선보고서 중 실험 자료가 필요한 항목

다음은 코드로 검사할 준비를 제공했지만 실제 연구 합격을 선언하지 않았습니다.

- 삼성 원본 시간축의 독립 시계 검증
- 실제 새 표식의 동적 중심·각도 정확도와 가림 후 ID 복구 성능
- 실제 ChArUco/격자의 holdout 오차
- 실제 FHD240 영상 50개 배치와 장시간 노트북 시험
- 실제 session holdout Farkas+IFR 예측, bootstrap CI의 반복실험 coverage
- 학생 3명의 독립 사용성 평가

## 이번 버전에 넣지 않은 고급 모델

- 전체 렌즈/H/법선의 공분산을 포함한 end-to-end 비선형 불확실성 전파
- rolling-shutter 행별 기하 보정. 현재는 입력 readout과 관측 속도로 영향 상한만 평가
- 완전한 MHT/JPDA. 현재는 모호성 검출과 trusted track 보호 후 수동 검토
- 계층 Bayesian/mixed-effects, 위치·속도 의존 마찰, 비균일 압력의 실측 모델 선택
- simultaneous 다체 충돌, 지속 접촉, 3D 들림 모델
- 독립 Windows installer/EXE. 현재 납품물은 설치·실행 도우미를 포함한 Python 소스 배포본

이 항목을 구현했다고 표시하지 않습니다. 근거 없는 파라미터나 검증 수치를 추가하는 대신 현재 결과의 적용 범위를 드러냅니다.

## 데이터 호환성

v1 `schema_version=1.0`은 읽을 때 2.0으로 변환합니다. 최초 저장 전 `project.v1.backup.json`을 만들며 원래 시간 변환은 유지합니다. 과거 `verified` 보정은 독립 오차 gate로 재평가합니다. 기존 run/cache는 남기고 새 code hash로 v2 분석을 만듭니다. 원본 영상은 수정하지 않습니다.
