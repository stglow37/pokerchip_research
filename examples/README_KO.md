# 예제 설정

pending 파일은 실제 실험으로 검증한 값이 아닙니다. 프로젝트 새 생성 후 GUI의 같은 종류 프로필에 가져와 필요한 실측값과 근거를 채우세요. project.pending.json을 직접 쓸 경우 빈 데이터 폴더에 project.json으로 복사합니다.

charuco_board의 square_m/marker_m, plane의 대응점·독립길이와 time profile의 근거는 반드시 실제 입력이 필요합니다. piecewise 예제의 factor8은 사용법 예시이며 삼성 파일에 자동 적용할 값이 아닙니다. 합성 fit dataset의 mass/계수/시간은 실제 칩으로 복사하지 않습니다.

영상 포함 전체 합성 예제는 run_cli.py demo 새폴더 명령으로 생성합니다.
