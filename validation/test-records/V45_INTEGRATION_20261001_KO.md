# v4.5 빠른 통합 검증 기록

- 날짜: 2026-10-01
- 환경: Windows, 사용 가능한 셸 Python 3.12.9(MSYS). 기존 `.venv`는 삭제된 CPython 3.13.3을 가리켜 실행 불가.
- 범위: v4.5 후보를 활성 코드베이스에 통합하고 사건 ID 안정성 및 칩 구간 범위 검증을 보완.
- 물리 지배식 변경: 없음.

## 실행 결과

1. `src/**/*.py`, `tests/**/*.py` AST 검사: **104 files OK**.
2. 표준 라이브러리 격리 스모크: 최초 분석과 재분석의 사건 ID 동일, 분석 범위 밖 칩 구간 거부: **PASS**.
3. 동봉 `validation/test-records/v45/pytest.xml`: **142 tests, 0 failures, 0 errors, 0 skipped** 확인. 이는 이번 환경의 재실행 결과가 아니다.
4. 동봉 release manifest 84개 항목 비교: 통합 전 일치. 통합 후 의도적으로 수정한 `application/pipeline.py`, `core/review.py`만 원본 릴리스 해시와 다름.
5. ZIP 무결성: 204 entries, `ZipFile.testzip()` 오류 없음.

새 회귀시험 2개를 추가했으므로 다음 전체 실행은 144개 이상 collection되어야 한다. 현재 환경에는 NumPy/SciPy/PySide6/pytest가 없어 전체 pytest와 GUI smoke를 재실행하지 않았다. 동봉 142개 성공 기록을 통합 후 코드의 새 실행 결과로 표현하지 않는다.

실제 영상 49개 기록은 자동 처리 통합 진단이다. 독립 중심·표식 정답이나 실제 물리계수 정확도 검증으로 승격하지 않는다.
