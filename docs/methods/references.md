# 참고 문헌과 구현 메모

외부 논문 PDF는 저작권과 저장소 이식성을 위해 이 저장소에 복사하지 않는다. 연구자가 보관한 원문 파일명은 다음과 같다.

- Doménech, A., Doménech, T. & Montagna, E., “Independent friction-restitution modeling of two-disk collisions,” *Physics of Fluids* 33, 043305 (2021). DOI: 10.1063/5.0044963. 원문 파일명: `DomenechMontagnaDomenech - Independent friction-restitution modeling of two-disk collisions (1) (1).pdf`.
- Farkas, Z. et al., 회전하며 미끄러지는 원판의 마찰 운동 모델, arXiv:physics/0210024. 이 연구에서 사용하는 분포 마찰 적분과 정지 상태 전이의 이론적 배경이다.
- 연구팀 작성 충돌 전·후 분석 문서. 원문 파일명: `창알논문_충돌전+충돌후_영어.pdf`.

## 원문과 구현의 차이

- Farkas 논문의 큰 `epsilon` 영역 토크 식은 인쇄본의 `4/(9π epsilon)` 대신 독립적인 접촉면 적분과 차원·극한 거동을 확인해 `4 epsilon/(9π)`로 구현했다. 이 선택은 [MODEL_DECISIONS_KO.md](MODEL_DECISIONS_KO.md)에 기록한다.
- IFR 문헌에서 관성 표기가 `I=mR/k`로 보이는 부분은 차원상 `I=mR²/k`로 해석한다.
- 충돌 계산은 법선·접선의 공통 임펄스를 부호가 있는 값으로 취급한다. 논문이 다루는 이상화된 두 원판 범위 밖의 손 접촉, 화면 이탈, 다중 접촉은 별도 품질 플래그와 검토 구간으로 관리한다.
- 구름 마찰은 현재 구현하지 않는다. 바닥 접촉은 미끄럼 마찰 모델이며, 거리·시간·관성의 명목값을 실제 독립 측정값으로 해석하지 않는다.
