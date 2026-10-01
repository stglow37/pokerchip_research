# 검증 자료 읽는 법

- `results/v4/summaries/video_summary.csv`: 영상 51개의 처리·개수·관측·운동학 비교표. 보정 2개는 별도 보정 지표를 사용합니다.
- `results/v4/summaries/video_inventory.json`: 원본 ID, 파일 크기, SHA-256.
- `results/v4/evidence/`: 보고서가 직접 인용하는 시각 증거, 보정 JSON, 물리 모델의 다른 영상 예측 검증.
- `validation/test-records/v4/`: 회귀 테스트 및 Qt 실제 버튼/프레임 선택 검증 기록.
- `scripts/reproduction/reproduce_v4_audit.py`: 원본 영상 폴더를 지정해 전체 녹화 진단을 재실행하는 도구.
- 동결 ZIP의 `baseline/`, `v4/`, `controlled_v35/`, `retries/`: 영상별 전체 산출물과 대조 실행. 관측률은 정답률이 아니며, 적절한 보정 후에도 기준선 문제가 그대로 발생한다는 뜻이 아닙니다.

재실행 예: `python scripts/reproduction/reproduce_v4_audit.py --videos D:/videos --output D:/v4_audit --workers 2`
보정 프로필은 이번 원본 영상 세션에만 대응합니다. 다른 촬영에 재사용하지 마세요.

전체 녹화 검사는 손 접촉·가림·화면 이탈을 포함합니다. 물리 계수 학습용으로 승인된 구간이라는 뜻이 아닙니다. 실제 GUI의 시작 프레임 확인은 유지됩니다.

CSV의 빈 값은 0이 아닙니다. `review_intervals.csv`의 프레임은 0부터 세는 디코딩 인덱스입니다. 충돌 후보와 검토 구간을 원본에 대조하세요. 상세 판정 기준은 `results/v4/reports/VALIDATION_REPORT_KO.md`에 있습니다.

전체 영상별 파일은 `archive/releases/v4.0.0/PokerChip_Astra_v4.zip`에서 확인합니다. 활성 저장소의 재현 스크립트는 입력과 출력 경로를 명시적으로 받습니다.
