# GitHub 공개 준비 안내

권장 저장소 이름은 `pokerchip_research`다. 소스, 시험, 방법·설계 문서, 공개 가능한 집계 검증 기록을 Git에 포함한다.

## Git에 포함하지 않는 로컬 자료

- `.venv/`: 기기·절대 경로 종속 가상환경. 새 위치에서 다시 생성한다.
- `work/`: 통합 전 복구 사본과 임시 추출·시험 결과.
- `runtime.local.json`, `.env*`, IDE 설정: 기기별 경로 또는 비밀정보 가능성이 있는 설정.
- `archive/**/*.zip`: 현재 v4 동결 ZIP은 약 85 MB다. 필요하면 GitHub Release 자산으로 별도 제공한다.
- `validation/test-records/v45/drive_inventory.json`: 원본 Google Drive 식별자와 공유 URL.
- `validation/test-records/v45/real_video_diagnostic.csv/json`: 원본 해시와 로컬 절대 실행 경로.
- `validation/test-records/v45/fit_result.json`, `evaluation_result.json`: 로컬 절대 결과 경로를 담은 포인터 파일.
- `results/v4/summaries/all_results.json`: 원본 Drive 식별자가 포함된 상세 로컬 요약.
- `results/v4/summaries/drive_recheck.json`: 원본 Drive 폴더 식별자를 담은 재확인 기록.
- `results/v4/summaries/video_inventory.json`: 원본 Drive URL·식별자와 영상 해시를 담은 인벤토리.

위 파일은 삭제 대상이 아니라 로컬 연구 증거다. 공개 저장소에는 집계 보고서, 코드 해시 manifest, 계수·검증 결과와 한계 설명을 남긴다.

## 복구 사본

`work/pre_v45_integration_20261001/`은 첫 Git 커밋과 원격 push를 확인할 때까지 유지한다. 원격 저장소와 태그가 정상적으로 복제되는 것을 확인한 뒤 삭제 여부를 결정한다. `work/`는 Git에서 제외된다.

## 공개 전 남은 결정

루트에 프로젝트 라이선스 파일이 아직 없다. 라이선스가 없으면 공개 열람은 가능하지만 다른 사용자의 복제·수정·재배포 권한이 명확하지 않다. GitHub 업로드 전에 MIT, BSD-3-Clause, Apache-2.0 또는 비공개/권리보유 중 하나를 연구 책임자가 선택해야 한다. `THIRD_PARTY_NOTICES.md`는 제3자 패키지 안내이며 프로젝트 자체 라이선스를 대신하지 않는다.
