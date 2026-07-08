# Provisional Tagging Audit Summary

## Corpus Counts

- Review files inspected: 89
- Wrong-answer records written: 89
- Active records used for tag analysis: 84
- Holdout records excluded from tag analysis: 5
- Needs-review records excluding holdouts: 2
- Holdout records requiring later re-solve: 5
- Records with missing canonical data: 0
- Source JSON parse repairs used without modifying originals: 1

Holdout records remain visible in `provisional_tags.jsonl`, but they are not active evidence for the provisional taxonomy and are excluded from tag frequency and final-promotion analysis.

## Active Tag Frequency Table

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

- Active low-confidence records: 1
- Holdout records are excluded from this count and from final tag promotion.
- `INSUFFICIENT_REVIEW_BASIS` is a temporary data-quality tag and should not be promoted as a final error mechanism.
- `CHOICE_VERIFICATION_FAILURE` should be reviewed carefully because it can become a secondary tag once a deeper mechanism is documented.

## Needs Review Records Excluding Holdouts

| Review file | Reason |
| --- | --- |
| data/reviews/2020 추리논증 홀수형/q40.review.json | 원본 review JSON에 쉼표 누락이 있어 좁은 in-memory repair로 읽었다. narrow in-memory JSON repair: Expecting ',' delimiter: line 28 column 5 (char 1147) |
| data/reviews/2025 언어이해 짝수형/q21.review.json | 사용자의 독립 리뷰 근거가 부족해 세트 연쇄 오류 가설만 가능하다. |

## Holdout Records

| Review file | Reason | Revisit plan |
| --- | --- | --- |
| data/reviews/2025 추리논증 짝수형/q09.review.json | No user self-review or assistant feedback is available. The user chose not to reconstruct the old reasoning from memory; this item should be re-solved later and then re-reviewed. | resolve_after_retake |
| data/reviews/2025 추리논증 짝수형/q23.review.json | No user self-review or assistant feedback is available. The user chose not to reconstruct the old reasoning from memory; this item should be re-solved later and then re-reviewed. | resolve_after_retake |
| data/reviews/2025 추리논증 짝수형/q29.review.json | No user self-review or assistant feedback is available. The user chose not to reconstruct the old reasoning from memory; this item should be re-solved later and then re-reviewed. | resolve_after_retake |
| data/reviews/2025 추리논증 짝수형/q33.review.json | No user self-review or assistant feedback is available. The user chose not to reconstruct the old reasoning from memory; this item should be re-solved later and then re-reviewed. | resolve_after_retake |
| data/reviews/2025 추리논증 짝수형/q34.review.json | No user self-review or assistant feedback is available. The user chose not to reconstruct the old reasoning from memory; this item should be re-solved later and then re-reviewed. | resolve_after_retake |

## Recommended Merge/Split Candidates

- Keep `SCOPE_CONDITION_MISAPPLICATION` separate from `GLOBAL_CONSTRAINT_DROPPED`: the former is about the scope of a condition, the latter about maintaining already-known global constraints.
- Consider splitting `TABLE_DIAGRAM_ENCODING_ERROR` later if quantity/unit mistakes become frequent enough to justify a dedicated quantitative-unit tag.
- Do not promote `INSUFFICIENT_REVIEW_BASIS`; current instances are holdouts and must be replaced after re-solving and review.
- Keep `TIME_PRESSURE_OR_ATTENTION_LAPSE` as primary only when the review itself identifies fatigue, time pressure, or direct input lapse as the main cause.

## Next Steps

1. Re-solve the holdout records, then add user self-review and assistant feedback before assigning mechanism tags.
2. Sample high-frequency tags against the original canonical question and passage records to confirm consistency.
3. Promote only stable mechanism tags from active records into `final_error_tags`; leave operational, insufficient-basis, and holdout tags out of final labels unless explicitly approved.
4. After promotion rules are settled, update the original review files in a separate, reviewed pass.
