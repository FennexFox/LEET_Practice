# Provisional Tagging Audit Summary

## Corpus Counts

- Review files inspected: 89
- Wrong-answer records tagged: 89
- Skipped correct-answer records: 0
- Records with missing or insufficient canonical data: 0
- Records marked needs_review for review-basis or source-data issues: 7
- Source JSON parse repairs used without modifying originals: 1

## Tag Frequency Table

| Tag | Primary count | Primary+secondary count |
| --- | --- | --- |
| `SCOPE_CONDITION_MISAPPLICATION` | 16 | 20 |
| `CONCEPT_LAYER_CONFUSION` | 12 | 17 |
| `ARGUMENT_STRUCTURE_INCOMPLETE` | 9 | 12 |
| `FORMAL_CONDITION_ERROR` | 9 | 12 |
| `CHOICE_VERIFICATION_FAILURE` | 8 | 12 |
| `GLOBAL_CONSTRAINT_DROPPED` | 8 | 9 |
| `TABLE_DIAGRAM_ENCODING_ERROR` | 6 | 11 |
| `RELATION_DIRECTION_REVERSAL` | 5 | 8 |
| `INSUFFICIENT_REVIEW_BASIS` | 5 | 5 |
| `ROLE_ATTRIBUTION_ERROR` | 4 | 5 |
| `UNWARRANTED_ASSUMPTION_ADDED` | 3 | 8 |
| `TEXTUAL_REDEFINITION_MISSED` | 2 | 7 |
| `TIME_PRESSURE_OR_ATTENTION_LAPSE` | 2 | 6 |

## High-Confidence Recurring Tags

- `SCOPE_CONDITION_MISAPPLICATION`: 16 primary records
- `CONCEPT_LAYER_CONFUSION`: 12 primary records
- `ARGUMENT_STRUCTURE_INCOMPLETE`: 9 primary records
- `FORMAL_CONDITION_ERROR`: 9 primary records
- `CHOICE_VERIFICATION_FAILURE`: 8 primary records
- `GLOBAL_CONSTRAINT_DROPPED`: 8 primary records
- `TABLE_DIAGRAM_ENCODING_ERROR`: 6 primary records
- `RELATION_DIRECTION_REVERSAL`: 5 primary records

## Low-Confidence Or Unstable Tags

- Low-confidence records: 6
- `INSUFFICIENT_REVIEW_BASIS` is intentionally unstable and should not be promoted as a final error mechanism.
- `CHOICE_VERIFICATION_FAILURE` should be reviewed carefully because it can become a secondary tag once a deeper mechanism is documented.

## Needs Review Records

| Review file | Reason |
| --- | --- |
| data/reviews/2020 추리논증 홀수형/q40.review.json | 원본 review JSON에 쉼표 누락이 있어 좁은 in-memory repair로 읽었다. narrow in-memory JSON repair: Expecting ',' delimiter: line 28 column 5 (char 1147) |
| data/reviews/2025 언어이해 짝수형/q21.review.json | 사용자의 독립 리뷰 근거가 부족해 세트 연쇄 오류 가설만 가능하다. |
| data/reviews/2025 추리논증 짝수형/q09.review.json | 사용자 self-review와 assistant feedback이 없어 canonical만으로 기제를 확정할 수 없다. |
| data/reviews/2025 추리논증 짝수형/q23.review.json | 사용자 self-review와 assistant feedback이 없어 canonical만으로 기제를 확정할 수 없다. |
| data/reviews/2025 추리논증 짝수형/q29.review.json | 사용자 self-review와 assistant feedback이 없어 canonical만으로 기제를 확정할 수 없다. |
| data/reviews/2025 추리논증 짝수형/q33.review.json | 사용자 self-review와 assistant feedback이 없어 canonical만으로 기제를 확정할 수 없다. |
| data/reviews/2025 추리논증 짝수형/q34.review.json | 사용자 self-review와 assistant feedback이 없어 canonical만으로 기제를 확정할 수 없다. |

## Recommended Merge/Split Candidates

- Keep `SCOPE_CONDITION_MISAPPLICATION` separate from `GLOBAL_CONSTRAINT_DROPPED`: the former is about the scope of a condition, the latter about maintaining already-known global constraints.
- Consider splitting `TABLE_DIAGRAM_ENCODING_ERROR` later if quantity/unit mistakes become frequent enough to justify a dedicated quantitative-unit tag.
- Do not promote `INSUFFICIENT_REVIEW_BASIS`; replace it after user self-review or assistant feedback is added.
- Keep `TIME_PRESSURE_OR_ATTENTION_LAPSE` as primary only when the review itself identifies fatigue, time pressure, or direct input lapse as the main cause.

## Next Steps

1. Review the needs_review records and add missing user self-review or assistant feedback before final promotion.
2. Sample high-frequency tags against the original canonical question and passage records to confirm consistency.
3. Promote only stable mechanism tags into `final_error_tags`; leave operational or insufficient-basis tags out of final labels unless explicitly approved.
4. After promotion rules are settled, update the original review files in a separate, reviewed pass.
