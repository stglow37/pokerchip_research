# 실행 검증 보고서

2026-09-27 / Windows 11 x64 / CPython 3.12.14. 수정 가능한 소스·GUI·CLI·문서·예제·검사와 최종 ZIP을 납품합니다. 실제 새 표식 FHD240의 계측 정확도·물리모델 실험 타당성은 별도 `pending_real_data`입니다.

## 환경과 설치

실행 host는 Windows 11 build26200, Intel64 Family6 Model197, 논리 CPU14, 물리 RAM 16,509,030,400bytes(약15.4GiB)입니다. 요청의 목표32GB 노트북과 동일 환경이라고 주장하지 않습니다. 외장 GPU는 사용하지 않았습니다.

프로그램 제작용 venv와 별개로 새 `clean_venv`를 생성해 requirements-lock 27개 고정 패키지를 설치하고, `pip install -e ... --no-deps --no-build-isolation`과 `pip check`를 실행했습니다. pip check는 `No broken requirements found`였습니다. 초기 샌드박스 네트워크 설치 시도는 WinError10013으로 실패했고 허용된 네트워크 설치로 재시도하여 완료했습니다. 의존성 버전/라이선스 메타데이터는 `validation/dependency_metadata.json`에 있습니다.

## 자동검사

최종 결과의 기준 기록은 `validation/pytest.xml`과 `verification_summary.json`입니다. 새 환경에서 **52개 검사 pass, 실패 0, 26.58초**를 확인하고 실제 결과를 해당 파일에 저장했습니다. 검사는 기대값을 동일 solver로 다시 계산하는 것만으로 구성하지 않았습니다.

| 구분 | 실제 수행 내용 | 상태 |
|---|---|---|
| Farkas | 14개 ε에서 독립 원판 면적적분, 해석 순수운동/정지, 혼합 에너지·부호·수렴 | pass |
| IFR | 다른 질량비/반경/I/spin, 선·각운동량/에너지, 공간회전·반사·label교환, branch경계, percussion 제한 | pass |
| 통합 solver | step 사이 고속 순차충돌2회, x/θ jump연속성, simultaneous unsupported | pass |
| 시간 | PTS→물리 factor8/구간 map, 미검증 gate, 중복/보간, 역행/불연속 거부 | pass |
| 기하·표식 | 합성12pose K 및 heldout, H/높이, 경계/공분산, 3ID, .42/.58R template, 한표식, 원형평균 | pass |
| 운동학·사건 | irregular polynomial, 충돌/결측 경계, unwrap ±π, 수동공분산, one-sided t_c/.8 정상비, sigma 증가 | pass |
| 저장·운영 | hash/relink, 같은basename, 취소checkpoint→clean 결과 일치, pause, atomic diskfull, 손상/소실 실패격리, 수정audit/cache | pass |
| GUI | 실제 Qt 위젯 합성생성→분석→scrub→중심클릭→undo/redo, 한글 screenshot | pass (QTest 자동조작) |
| 피팅 | 독립해석 궤적/별도 impulse noisy fixture 회복, 식별성/누수gate, bootstrap smoke | pass |

최종 테스트 개수와 실행 시간은 XML에 기록된 값으로 확인하세요. 테스트 픽셀 허용치는 해당 합성 영상 조건에만 적용되며 보편적 정확도 보증이 아닙니다.

ZIP을 별도 폴더에 압축 해제하고 새 환경의 editable 설치 대상을 그 폴더로 바꿔 다시 검증했습니다. CLI 도움말 실행과 **52개 검사 pass, 실패0, 30.50초**를 확인했습니다. `pytest_extracted.xml`이 그 기록입니다. ZIP CRC, 금지 파일/개인 로컬 경로 제외, JSON parse, 문서 링크, R01–R31 항목 존재 검사도 통과했습니다.

## 합성 end-to-end와 피팅

640×400, 60fps, 60frame의 3칩 합성 영상 생성→분석→CSV/JSON/XLSX/그래프를 새 환경에서 실행했습니다. 관측 행/유효 물리 미분 수는 `demo_quality.json`, 그래프는 `demo_trajectories.png`입니다. 합성 데모 궤적은 UI/계측 검사용으로 만들어져 Farkas 물리 일치 자체를 보장하지 않습니다.

별도 independent fit fixture는 순수 병진 해석식과 별도로 구성한 충격량으로 noisy 관측을 만들었습니다. session_0/1 학습, session_2 보류입니다.

| 계수 | 정답 | 추정 |
|---|---:|---:|
| μ_b | 0.12 | 0.1201531 |
| e_n | 0.72 | 0.7198294 |
| e_t | −0.83 | −0.8326546 |
| μ_c | 0.08 | 0.0802935 |

bootstrap 4회는 코드 실행 검사입니다. 신뢰구간 안정성이나 실험 coverage를 검증한 결과가 아닙니다. 진단·단위별 holdout/조건부 coverage·전후 상태/충격량은 `fit_synthetic.json`에 있습니다.

## 이미지 stress와 운영 자원

원근 homography로 합성 원/표식을 투영하고 3개 시야 위치×clean/blur/noise/shadow/occlusion의 15조건을 계측했습니다. **정답 후보 중심을 제공한 최종 계측 검사**이며 검출 recall 검사는 아닙니다. clean/blur/noise/shadow의 원본 환산 중심 오차는 약0.43~0.61px, 부분 가림에서는 약0.73~2.86px였습니다. 가림 조건은 low_confidence 또는 partially_observed였습니다. 짧은 호/가림에서는 작은 fit 잔차가 실제 중심 편향을 보장하지 않음을 확인했습니다. 원근·렌즈왜곡·가림·빛반사가 동시에 변하는 모든 촬영 조건을 검증한 것은 아닙니다.

| 배치 | 결과 | 시간 | 표본 RSS 최대 |
|---|---|---:|---:|
| 52개 고유 synthetic H264, 각640×400/60fps/4frame + 손상1 | 정상52 완료, 손상1만 실패, 이후 정상 계속 | 49.72s | 212,037,632bytes(202.2MiB) |
| 연속2000frame synthetic H264,640×400/240fps | 완료 | 103.61s | 212,631,552bytes(202.8MiB) |

2000frame에서 검출 초기 약169MiB, 중반 약173MiB, 운동학 약176MiB, export 포함 최대 약203MiB였습니다. 전체 프레임을 보관하는 구조가 아닌지 확인하는 제한적 검사입니다. 시간은 작업 시작~완료이며 합성 파일 생성 시간은 제외했습니다. RSS는 callback 표본이므로 OS가 측정한 절대 peak와 다릅니다. 측정 당시 빌드 이후 후보 밝기 필터/캐시 메타데이터 검사를 보강했으며 최종 기능검사는 별도 재실행했습니다. 이 수치를 실제 FHD240 처리량이나 수시간 soak로 확대하지 않습니다.

## 제공된 과거 영상

원본 HEVC1920×1080, 표시 회전 후1080×1920. `1개_004.mp4`는119frame, `2개_001.mp4`는121frame이며 재생 metadata는 약60fps입니다. 실제 촬영 시간의 독립 근거는 없으므로 physical time/속도/각속도는 null로 유지했습니다. 고정 새 표식은 없으므로 `legacy_unknown`으로 ID를 처리했습니다.

최종 검토 실행: 단일 영상77/119 chip-frame, 2칩 영상163/242 chip-frame의 관측 행을 얻었습니다. **이는 정답 recall이 아니며, 불완전한 과거 영상 추적 결과입니다.** 2칩 영상의 low_confidence 관측26개, 승인된 사건0개입니다. 이를 충돌계수 추정에 사용하지 않았습니다. 화면 이탈·발사 구간·기존 반복 rim 문양·motion blur의 영향이 남습니다. 세부 hash/run/품질은 `provided_videos.json`에 있습니다.

디코딩·분석·표/그림·overlay 출력은 완료했고, 선택한 overlay 프레임을 직접 비교했습니다. 초기 버전의 격자 교차점 오검출을 발견하여 검은 칩 내부/외부 대비와 내부 밝기 prior를 추가했습니다. 이전의 관측행100%는 성공률로 폐기했습니다. 최종 출력은 실패/결측을 보존하며 예측 좌표로 채우지 않습니다. 원본과 검토 MP4는 용량/사용자 자료 분리를 위해 프로그램 ZIP에 포함하지 않았고, 로컬 검증 작업 폴더에 보존했습니다.

## 실패 후 수정한 항목

- 제공 Farkas ε>1 토크 인쇄식이 독립 면적적분과 불일치하여 앞계수를 ε 배로 재구성. 모델결정 문서에 원문과 검산값 기록.
- unknown ID 승격 중 오래된 key 접근으로 발생하던 오류와 참여 칩 수 초과 관측을 수정하고 회귀검사 추가.
- 격자/발사기 오검출을 실제 overlay 비교에서 발견해 dark-face prior 추가. 신규 칩 면이 검지 않으면 별도 detector 연구 필요.
- 연속 θ의2π gauge, 수동 중심공분산, 발사 제외구간/조건 변경의 캐시 무효화를 보강.
- GUI offscreen 한글 fallback 및 자동검사의 thread 이벤트 대기를 수정. 실제 렌더된 screenshot을 포함.

## not_run / pending_real_data

| 항목 | 상태와 이유 |
|---|---|
| 실제 native240 독립clock·새 marker 동적정확도·실측물성 피팅 | pending_real_data: 원본/실측자료 미제공 |
| 실제 ChArUco calibration 영상·별도 실제 길이/각도 기준 | pending_real_data |
| 실제 실험 정지/보존량 residual·CI coverage·model mismatch | pending_real_data |
| 사람의 전체 GUI 수동 smoke, 다른32GB 노트북 설치 | not_run: 현재 host/QTest 자동조작으로 검증 |
| 수시간 soak, 실제50개 FHD240 처리시간 | not_run: 작은 배치와2000frame 검사만 수행 |
| OS강제kill 타이밍 전조합·실제 디스크 고갈·실제 권한ACL 차단·특정 unsupported codec별 시험 | not_run: 협력취소+checkpoint/모의diskfull/손상·소실 격리 검사로 한정 |
| 실제 심한 lensdistortion+blur+reflection+가림 동시조건의 recall/ID switch | pending_real_data; 합성 일부조건만 검사 |

## 재현 명령

프로젝트 루트에서 `python`은 검증한 venv의 실행파일을 의미합니다.

```powershell
python -m pip check
python -m pytest -q --junitxml=work\pytest.xml
python run_cli.py demo "work\demo" --frames 60
python run_cli.py analyze "work\demo"
python run_cli.py fit "work\demo\fit_dataset.synthetic.json" "work\fit" --bootstrap 4
python tools\benchmark_queue.py "work\batch52"
python tools\validate_extended.py "work\extended" --frames 2000
python tools\validate_samples.py "기존영상폴더" "work\legacy"
```

출력 폴더는 새 경로를 지정합니다. 기존 사용자의 원본 파일을 덮어쓰거나 지우는 작업은 하지 않았습니다.
