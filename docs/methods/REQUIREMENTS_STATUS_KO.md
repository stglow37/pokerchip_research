# R01–R31 구현·검증 대조표

2026-09-27 / 버전 1.0.0. `구현`은 실행 경로가 있다는 뜻이며 실물 정확도 합격을 의미하지 않습니다. 검사는 `tests/`와 `validation/`에 연결됩니다. 실제 새 표식/FHD240 실험은 전체적으로 `pending_real_data`입니다. 미실행 검사는 [검증 보고](../../results/v4/reports/VALIDATION_REPORT_KO.md)에 별도 표시합니다.

| ID | 구현 파일 (src/pokerchip 아래) | 수행 검사/증거 | 상태와 제한 |
|---|---|---|---|
| R01 | config, cli, gui, pipeline | operations/GUI tests, 새 환경 설치 | 구현. 같은 엔진 사용, 프로필 JSON 편집 UI |
| R02 | gui, config, jobs | 52개 서로 다른 합성 파일+동일 basename 배치 | 구현. 조건 다중/개별 수정, 실물50개 FHD240 속도 미검증 |
| R03 | config, storage, pipeline | hash/relink, run/cache tests | 구현. 외부 원본 읽기, 상대 경로, 원본 보존 |
| R04 | vision, tracking, pipeline | 3칩 합성, unknown/참여수 상한, 격자 거부 | 구현. 자동 수는 후보 제안, 최종 참여수는 사용자 설정 |
| R05 | video, timebase | PTS·회전·slow fixture, 제공 HEVC 디코딩 | 구현. 노출 정보가 없으면 midpoint null |
| R06 | timebase, gui | factor8/구간 연속·양수 검사 | 구현. verified evidence 필수, 삼성실물 독립 clock 대기 |
| R07 | timebase, analysis, fitting | pending end-to-end, 중복/보간 gate | 구현. 미확정 시간에서 물리 속도/fit 차단 |
| R08 | calibration, gui, cli | 합성12pose K 복원 및 heldout 점 | 구현. 보정 영상 drop/선택, 실물 ChArUco 영상 대기 |
| R09 | calibration, pipeline, gui | 독립 대응점 H/holdout, ray-plane | 구현. fixed H와 drift 경고, 실물 길이 대기 |
| R10 | calibration, pipeline | h>0 합성 ray-plane roundtrip | 구현. 각 칩 두께 반영, pose/두께 없으면 height_unverified |
| R11 | vision | 원본 경계/짧은 호 공분산/원근 stress | 구현. Hough는 후보만, subpixel+robust 원; 공분산은 조건부 |
| R12 | vision, calibration | 투영 원15조건 stress | 구현. world 원 재투영 원본 샘플 반복. 심한 원근/가림 정확도 보증 없음 |
| R13 | vision, video, tracking | 격자/그림자/노이즈/blur/가림, 제공영상 overlay 검토 | 구현. 검은 면 대비 prior 사용. 가림 최대2.86px 상당 편향 관찰; 경고/수동 검토 필요 |
| R14 | vision, gui | .42/.58R 표식·circular template 검사, GUI 화면 | 구현. 클릭 색·상대각·반경비 학습, 선명도 기준 프레임 제안 |
| R15 | vision, analysis | 한 표식 missing·±179° fusion·alias gate | 구현. arbitrary multi-turn은 복원 보장 안 함 |
| R16 | tracking, pipeline, storage | 3ID·가림 예측 분리·unknown→ID 회귀검사 | 구현. assignment 모호 표시, 실물 ID-switch 정답 대기 |
| R17 | analysis | irregular polynomial·경계 분할·연속 unwrap | 구현. 결측/충돌/발사 제외 창, SI 미분과 sigma |
| R18 | analysis | one-sided t_c=.2 fixture, sigma 확대 | 구현. 선형화 fit+반경+선택 공통 scale/clock. 총 비선형 오차 coverage 미검증 |
| R19 | analysis, physics/ifr | 양쪽 spin c, impulse 항등식 | 구현. 입사/산란/부호 b 정의, 저속 null |
| R20 | analysis, simulator, gui | contact graph와 simultaneous unsupported | 구현. out-of-plane은 수동 영상 판정 가능; 자동3D 재구성 없음 |
| R21 | physics/farkas | 14ε 독립면적적분, 순수/혼합/정지/수렴 | 구현. 인쇄 토크식 ε>1 수정 결정 문서화, 공식 정오표 주장 안 함 |
| R22 | physics/ifr | 질량비 .5/1/2, spin·보존·대칭·두branch·passivity | 구현. contact 확장과 제한 percussion 명시, 실험검증 대기 |
| R23 | physics/simulator | frame사이 고속2충돌, 상태연속/동시다체 차단 | 구현. 다체/지속접촉은 unsupported, 임의 순서 적용 안 함 |
| R24 | fitting, research, gui | 독립해석/impulse noisy fixture 계수복원 | 구현. 직접 위치·각도, trial초기값, EIV, 공통scale bootstrap |
| R25 | fitting, validation | bounds·rank·비식별·split·bootstrap smoke | 구현. optimizer/식별/물리상태 분리. 소표본 CI를 확정값으로 사용 금지 |
| R26 | validation, fitting, research | 단위별 RMSE/MAE/coverage, holdout, stop/invariants | 구현. free/조건부/완전예측 분리. 실험정지·coverage·model mismatch 대기 |
| R27 | gui, storage | 실제 Qt widgets 생성→분석→scrub→중심→undo/redo | 구현. 거리/품질 그래프, 사건, 표식/ID/호/각도 수정. 사람 전체 수동 smoke는 not_run |
| R28 | jobs, pipeline, storage | pause/cancel/checkpoint 등가·diskfull·실패격리·52파일·2000frame RSS | 구현. 기본1worker. 수시간실험/강제 OS kill 반복/실제RAM32GB 검증 미실행 |
| R29 | exporting, research | CSV/JSON/XLSX sheet, 그래프·overlay 디코딩 | 구현. 주요 CSV+전체 JSONL, 대량 원시 궤적 Excel강제 없음 |
| R30 | storage, config, pipeline | key 의존단계·hash/relink·수정audit 검사 | 구현. 코드/모델/설정/seed/split run 연결 |
| R31 | README, docs, examples, requirements-lock | Python3.12 새 venv 설치·테스트, demo | 구현. 초보자 매뉴얼·pending 예제·실행 증거·제약 제공 |

원문 요구사항이 요구한 모든 세부 실험 조건을 이미 검증했다고 주장하지 않습니다. 구현 범위 밖인 진짜 다체/3D/rolling/환형압력 모델과 실제 데이터가 필요한 연구 검증은 숨겨진 자동 대체 없이 명시적으로 남겼습니다.
