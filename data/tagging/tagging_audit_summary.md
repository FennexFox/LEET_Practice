# Provisional Tagging Audit Summary

## Corpus Counts

- Review files inspected: 112
- Wrong-answer records written: 112
- Active records used for tag analysis: 112
- Holdout records excluded from tag analysis: 0
- Needs-review records excluding holdouts: 1
- Holdout records requiring later re-solve: 0
- Records with missing canonical data: 0
- Source JSON parse repairs used without modifying originals: 0

No holdout records are currently present in `provisional_tags.jsonl`.

## Active Tag Frequency Table

| Tag | Primary count | Primary+secondary count |
| --- | --- | --- |
| `SCOPE_CONDITION_MISAPPLICATION` | 22 | 27 |
| `CONCEPT_LAYER_CONFUSION` | 20 | 27 |
| `TABLE_DIAGRAM_ENCODING_ERROR` | 13 | 16 |
| `GLOBAL_CONSTRAINT_DROPPED` | 11 | 14 |
| `FORMAL_CONDITION_ERROR` | 10 | 17 |
| `ARGUMENT_STRUCTURE_INCOMPLETE` | 9 | 12 |
| `UNWARRANTED_ASSUMPTION_ADDED` | 6 | 13 |
| `TEXTUAL_REDEFINITION_MISSED` | 6 | 12 |
| `CHOICE_VERIFICATION_FAILURE` | 5 | 17 |
| `RELATION_DIRECTION_REVERSAL` | 4 | 9 |
| `ROLE_ATTRIBUTION_ERROR` | 4 | 5 |
| `TIME_PRESSURE_OR_ATTENTION_LAPSE` | 2 | 7 |

## High-Confidence Recurring Tags

- `SCOPE_CONDITION_MISAPPLICATION`: 22 primary records
- `CONCEPT_LAYER_CONFUSION`: 20 primary records
- `TABLE_DIAGRAM_ENCODING_ERROR`: 13 primary records
- `GLOBAL_CONSTRAINT_DROPPED`: 11 primary records
- `FORMAL_CONDITION_ERROR`: 10 primary records
- `ARGUMENT_STRUCTURE_INCOMPLETE`: 9 primary records
- `UNWARRANTED_ASSUMPTION_ADDED`: 6 primary records
- `TEXTUAL_REDEFINITION_MISSED`: 6 primary records
- `CHOICE_VERIFICATION_FAILURE`: 5 primary records

## Low-Confidence Or Unstable Tags

- Active low-confidence records: 1
- Holdout records are excluded from this count and from final tag promotion.
- `INSUFFICIENT_REVIEW_BASIS` is a temporary data-quality tag and should not be promoted as a final error mechanism.
- `CHOICE_VERIFICATION_FAILURE` should be reviewed carefully because it can become a secondary tag once a deeper mechanism is documented.

## Needs Review Records Excluding Holdouts

| Review file | Reason |
| --- | --- |
| data/reviews/2025 언어이해 짝수형/q21.review.json | 사용자의 독립 리뷰 근거가 부족해 세트 연쇄 오류 가설만 가능하다. |

## Holdout Records

- None.

## Recommended Merge/Split Candidates

- Keep `SCOPE_CONDITION_MISAPPLICATION` separate from `GLOBAL_CONSTRAINT_DROPPED`: the former is about the scope of a condition, the latter about maintaining already-known global constraints.
- Consider splitting `TABLE_DIAGRAM_ENCODING_ERROR` later if quantity/unit mistakes become frequent enough to justify a dedicated quantitative-unit tag.
- Do not promote `INSUFFICIENT_REVIEW_BASIS`; any future instance should remain a holdout until fresh self-review and feedback are available.
- Keep `TIME_PRESSURE_OR_ATTENTION_LAPSE` as primary only when the review itself identifies fatigue, time pressure, or direct input lapse as the main cause.

## Next Steps

1. If a future record lacks review evidence, hold it out until re-solving, user self-review, and assistant feedback are complete.
2. Sample high-frequency tags against the original canonical question and passage records to confirm consistency.
3. Promote only stable mechanism tags from active records into `final_error_tags`; leave operational, insufficient-basis, and holdout tags out of final labels unless explicitly approved.
4. After promotion rules are settled, update the original review files in a separate, reviewed pass.
