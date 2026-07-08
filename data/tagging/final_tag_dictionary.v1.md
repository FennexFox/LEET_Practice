# Final Error Tag Dictionary v1

This file defines the first promoted mechanism tags for LEET wrong-answer review. These tags are stable enough to use as `final_error_tags` candidates after per-record confirmation. They are distinct from supporting tags and status tags.

## Promoted mechanism tags

| Tag ID | Korean display name | Core mechanism |
| --- | --- | --- |
| `SCOPE_CONDITION_MISAPPLICATION` | 범위·조건 오적용 | 조건·예외·단서·경계값·가능성/보장 관계를 과확장하거나 과축소하여 선지가 요구하는 강한 결론을 부당하게 인정하거나 배척한 오류. |
| `CONCEPT_LAYER_CONFUSION` | 개념 층위 혼동 | 지문이 구분하는 판단 층위, 예컨대 결과/정당화, 지위/평가, 내용/태도, 대상/표상, 원리/적용을 섞어서 선지를 판단한 오류. |
| `ARGUMENT_STRUCTURE_INCOMPLETE` | 논증 구조 미완성 | 주장, 근거, 중간결론, 반박 대상, 귀류, 강화/약화 관계 등 논증의 연결 구조를 끝까지 완성하지 못해 선지의 지지·반박 방향을 오판한 오류. |
| `FORMAL_CONDITION_ERROR` | 형식 조건 처리 오류 | 부등식, 절댓값, 존재·전칭 양화, 필요·충분조건, 예산식, 순서식 등 형식화해야 할 조건을 잘못 세우거나 잘못 조작한 오류. |
| `GLOBAL_CONSTRAINT_DROPPED` | 전역 제약 누락 | 국소 계산·판단은 맞았지만 남은 경우의 수, 상위 규칙, 전체 표 구조, 공통 제약, 새로 발견한 규칙을 전체 선지 판단에 끝까지 유지하지 못한 오류. |
| `TABLE_DIAGRAM_ENCODING_ERROR` | 표·도식·변수 인코딩 오류 | 표, 도식, 그래프, 실험 설계, 변수 비교, 수치 임계값, 기호 라벨을 선지 판단 전에 올바른 문장·식·비교쌍으로 재부호화하지 못한 오류. |
| `RELATION_DIRECTION_REVERSAL` | 관계 방향 전도 | A→B, 원인→결과, 주는 사람→받는 사람, 현재→목표, 입력→출력처럼 방향성이 명시된 관계를 반대로 잡은 오류. |
| `TEXTUAL_REDEFINITION_MISSED` | 지문 정의 전환 누락 | 지문이 개념·용어·기준·방식어를 특수하게 정의하거나 대비시켰는데 일반적 의미나 다른 변화 방식으로 처리한 오류. |
| `UNWARRANTED_ASSUMPTION_ADDED` | 무근거 가정 추가 | 지문이나 조건이 허용하지 않은 전제, 배경 설명, 경로, 사례, 일반론을 덧붙여 선지를 살리거나 배척한 오류. |

## Use rules

- Assign one primary final mechanism whenever the review and canonical structure support it.
- Add secondary mechanism tags only when they explain a distinct part of the error, not merely the final verification failure.
- Do not promote `INSUFFICIENT_REVIEW_BASIS` into final tags.
- Use `CHOICE_VERIFICATION_FAILURE` only as a supporting tag unless no deeper mechanism is recoverable.
- Use `TIME_PRESSURE_OR_ATTENTION_LAPSE` as an operational modifier, not as a mechanism tag, except where the record itself identifies attention/time failure as the primary cause.

## Provisional tags not promoted in v1

`ROLE_ATTRIBUTION_ERROR` remains a provisional mechanism candidate. It has clear examples, but v1 keeps the final tag set focused on the higher-frequency, better-separated mechanisms. Revisit it after additional representative-case review.
