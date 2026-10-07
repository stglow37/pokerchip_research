# 설계 결정 기록(ADR)

ADR은 이미 채택한 중요한 결정을 왜 유지하는지 기록한다. 현재 코드 설명은 [아키텍처](../architecture/ARCHITECTURE_KO.md), 물리식의 상세 정본은 [MODEL_DECISIONS_KO.md](../methods/MODEL_DECISIONS_KO.md)다.

- [ADR-001: CLI와 GUI는 같은 application service를 사용한다](ADR-001-cli-gui-shared-services.md)
- [ADR-002: 불변 측정 스냅샷과 현재 물리 설정을 구분한다](ADR-002-measurement-snapshot-current-physics.md)
- [ADR-003: 위치 기반 법선 반발과 회전 기반 IFR를 분리한다](ADR-003-normal-restitution-and-ifr-separation.md)
- [ADR-004: 검색 후보와 운동학 사건 장벽을 분리한다](ADR-004-reviewed-event-barriers.md)
- [ADR-005: 계산 단계별 canonical 코드 digest를 사용한다](ADR-005-stage-specific-code-digests.md)
- [ADR-006: v4.5 검토·계산 계약을 추가형 schema로 적용한다](ADR-006-v45-review-contract.md)
- [ADR-007: v5 관측 우선 자동 계측](ADR-007-v5-observation-first.md)
- [ADR-008: v6 경고 포함 계산·계층 집계·관측 통합](ADR-008-v6-warning-and-integration.md)

새 ADR은 `ADR-NNN-short-name.md`로 추가하고 상태, 날짜, 맥락, 결정, 결과, 재검토 조건을 포함한다. 기존 결정을 바꾸면 원문을 삭제하지 말고 `superseded by ADR-NNN`으로 연결한다.
