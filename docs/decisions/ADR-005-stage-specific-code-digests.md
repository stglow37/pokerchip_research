# ADR-005: 계산 단계별 canonical 코드 digest를 사용한다

- 상태: accepted
- 날짜: 2026-09-30

## 맥락

구조 재편 뒤 일부 application 파일만 해시하면 measurement, analysis, physics 구현이 바뀌어도 과거 캐시가 재사용될 수 있다. 반대로 UI나 호환 import 변경까지 모든 과학 결과를 무효화하면 불필요한 재분석이 발생한다.

## 결정

measurement, analysis, physics, export 단계별로 canonical 구현 파일 manifest와 digest를 계산한다. 공통 core는 보수적으로 포함한다. UI와 이전 import shim은 과학 digest에서 제외한다. run manifest에는 전체 digest와 단계별 `code_hashes`를 함께 기록한다.

## 결과

- 과학 코드 변경은 관련 캐시를 무효화한다.
- UI 문구와 호환 shim 변경은 원칙적으로 측정 결과를 무효화하지 않는다.
- 한 파일에 여러 단계 구현이 섞이면 안전한 false cache miss가 발생할 수 있다.
- canonical 디렉터리를 추가할 때 `CODE_SCOPES`와 회귀시험을 갱신해야 한다.

## 재검토 조건

단계 구현이 별도 패키지나 build artifact로 분리되면 파일 집합 digest를 배포 artifact digest로 대체할 수 있다. 이전 manifest 판독은 유지한다.
