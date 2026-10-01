# ADR-001: CLI와 GUI는 같은 application service를 사용한다

- 상태: accepted
- 날짜: 2026-09-30

## 맥락

프로젝트는 Windows GUI에서 시작했지만 대량 처리, 재현, 자동 검증에는 headless CLI가 필요하다. 두 경로가 각자 검출·운동학·물리 계산을 구현하면 결과가 달라지고 한쪽 수정이 다른 쪽에 반영되지 않는다.

## 결정

CLI와 GUI는 입력 수집과 표시만 다르게 하고 `application`, `analysis`, `models`의 같은 함수를 호출한다. 과학 계산과 결과 schema는 UI 모듈에 구현하지 않는다. GUI는 선택적 도구이며 패키지의 필수 계산 계층이 아니다.

## 결과

- 동일 입력과 review spec은 진입점과 관계없이 같은 과학 결과를 만들어야 한다.
- application service는 Qt 객체가 아닌 직렬화 가능한 입력·출력을 사용해야 한다.
- CLI 간편 흐름을 추가할 때 기존 GUI 코드를 호출하지 않는다.
- GUI 전용 진행·취소 adapter는 허용하지만 계산 의미를 바꾸지 않는다.

## 재검토 조건

특정 상호작용이 GUI에서만 표현 가능하다면 먼저 저장 가능한 review spec으로 모델링할 수 있는지 검토한다. 별도 계산 경로는 독립 schema와 동등성 시험 없이 허용하지 않는다.
