# ADR-009: 원형 접촉면의 비균일 마찰장 탐색 모델

2026-10-10. 상태: 연구용 후보. 실험적으로 확정된 원인 또는 기본 모델이 아니다.

사용자는 모든 원본 영상 검증과, 필요시 이론·프로그램 개선을 요청했다. 원본·기존 결과를 보존하고 별도 추출본에서 작업한다. 물체는 원형 밑면을 가진 얇은 균질 원기둥으로 가정한다. 원형 밑면 자체는 균일 압력·균일 마찰계수를 증명하지 않는다.

기존 Farkas/IFR 식과 기본 실행 경로는 유지한다. 새 `models/contact_field.py`는 독립적으로 호출하는 탐색 모듈이다. CSV·JSON·CLI schema를 바꾸지 않는다.

## 가정과 식

질량중심 좌표 r=(x,y), 반지름 R, I=kappa*m*R^2, kappa=1/2이다. 몸체 좌표 rho를 theta만큼 회전해 r를 얻는다. 국소 미끄럼은 u=v+omega*z_cross*r이다. 균일 정상압력 p=mg/(pi*R^2) 아래 국소 마찰계수를 mu(rho)=mu0+mux*rho_x/R+muy*rho_y/R로 두고, mu0>=sqrt(mux^2+muy^2)를 강제한다. 따라서 접촉면 전체에서 마찰이 음수가 되지 않는다.

F=-integral p*mu*u/|u| dA, tau=-integral p*mu*(r cross u)_z/|u| dA, m*vdot=F, I*omegadot=tau.

운동에너지 변화율은 F dot v+tau*omega=-integral p*mu*|u| dA<=0이다. tau*omega>0은 가능하지만 이때 병진 에너지 감소가 회전 에너지 증가보다 크다. 회전 대칭인 mu와 p에서는 마찰 소산함수가 omega에 대해 짝함수·볼록함수이므로 omega*tau<=0이다. 따라서 마찰계수의 값만 바꾸거나 방사 대칭 압력만 바꾸는 것으로 자유운동의 지속적인 회전 증가를 설명할 수 없다.

여기서 비대칭 변수는 **유효 마찰 강도**이다. 이것을 실제 압력 분포로 단정하지 않는다. 유한 높이 원기둥의 압력은 수평축 모멘트 평형까지 만족해야 하며 임의로 정할 수 없다. 이 구현은 사용자가 지정한 얇은 원기둥 근사의 평면 운동 모델이다. 기울기·들림·발사 접촉·강체성 위반은 별도 진단한다.

## 수치 구현과 검증

원판의 r^2에 Gauss-Legendre 적분, 각도에 균등 중점 적분을 사용한다. 12x48점이 기본이다. 속도 정규화의 epsilon=1e-6 m/s와 예측 정지 문턱 0.003 m/s는 수치 설정이며 관측 정확도가 아니다. 예측 시 최초 상태 뒤에 관측 상태를 다시 주입하지 않는다. 충돌은 별도 IFR 검토 대상이며 이 모듈은 자유운동 전용이다.

면적·관성 모멘트, 순수 병진/회전 극한, 국소 일률 항등식, 에너지 단조성, 시간 간격 수렴을 시험한다. 합성 회전 증가 예시는 기전의 가능성만 입증하며 실험 원인 입증으로 쓰지 않는다.

## 반증과 선택

비대칭 계수는 개발·학습 영상에서만 추정한다. 기존에 예약한 보류 영상은 친구 결과에 이미 쓰인 2개를 제외한 58개로 유지한다. 코드를 수정하거나 계수를 선택하기 전에 이 보류군의 물리 진단 결과를 열지 않는다. 후보가 보류군 예측을 개선하지 않으면 이론의 가능성과 해당 실험의 설명력을 구분하고 채택을 보류한다. 영상에서 역산되는 것은 mu*p의 효과이며 둘을 별도로 식별했다고 주장하지 않는다.

## 문헌

- Farkas et al., Frictional coupling between sliding and spinning motion: https://arxiv.org/abs/physics/0210024
- Goyal, Ruina, Papadopoulos, Limit surface and moment function descriptions of planar sliding: https://doi.org/10.1109/ROBOT.1989.100081
- Antali, Harmonic expansion and nonsmooth dynamics in a circular contact region with combined slip-spin motion (2024): https://doi.org/10.1007/s11071-024-09462-6

위 문헌은 분포 접촉 마찰과 힘·토크 결합의 근거다. 본 첫 조화 마찰장 파라미터화와 이번 실험에 대한 적용은 이 작업의 탐색적 선택이다.
