# ADR-002: 불변 측정 스냅샷과 현재 물리 설정을 구분한다

- 상태: accepted
- 날짜: 2026-09-30

## 맥락

완료 run의 관측과 운동학은 당시 시간·기하·검출 설정에 의존한다. 반면 질량·관성·충돌 모델은 후속 연구에서 명시적으로 갱신될 수 있다. 과거 run의 모든 설정을 그대로 쓰면 최신 물성을 무시하고, 현재 설정을 전부 덮으면 관측 provenance가 깨진다.

## 결정

후속 피팅은 run의 `effective_settings.json`에서 측정·시간·기하 설정을 유지한다. 현재 프로젝트에서 선택한 chips 물성, physics, fit split, seed만 명시적으로 결합한다. 현재 설정으로 계산한 analysis key가 run과 다르면 재분석을 요구한다.

`measurement_settings_hash`, `physics_settings_hash`, `physical_settings_source`를 provenance에 기록한다.

## 결과

- 측정 결과가 어떤 설정에서 만들어졌는지 추적할 수 있다.
- 질량·관성 변경은 물리 단계에서 명시적으로 반영된다.
- 반지름처럼 측정과 물리 양쪽에 영향을 주는 변경은 analysis key 검사로 재분석될 수 있다.
- 설정 병합 필드를 늘릴 때 provenance와 무효화 시험을 함께 갱신해야 한다.

## 재검토 조건

Schema 3.0 artifact graph가 각 입력을 독립 참조하게 되면 필드 단위 결합을 artifact 참조로 대체할 수 있다. 기존 run 재현 가능성은 유지해야 한다.
