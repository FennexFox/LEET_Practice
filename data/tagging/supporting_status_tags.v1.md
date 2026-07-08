# Supporting and Status Tags v1

These tags should not normally be promoted as primary final error mechanisms. They explain verification behavior, operational state, or data quality.

## Supporting tags

### `CHOICE_VERIFICATION_FAILURE`

- Korean display name: 선지 검산 실패
- Role: supporting tag
- Meaning: A plausible selected choice, eliminated choice, or answer candidate was not finally checked against the exact passage, condition, or selected/correct choice relationship.
- Use when: the error is specifically about final answer confirmation, such as failing to revisit an initially skipped choice, over-focusing on a hard choice, or confusing information insufficiency with contradiction in an exclusion-style question.
- Do not use as primary when: a deeper mechanism such as condition-scope failure, concept-layer confusion, formal-condition error, or table/variable encoding error explains the wrong answer.
- Correction rule: before marking, pair the selected choice with one exact passage/condition support or conflict point.

### `TIME_PRESSURE_OR_ATTENTION_LAPSE`

- Korean display name: 시간 압박·주의 저하
- Role: operational modifier
- Meaning: fatigue, time pressure, rushed reading, direct input lapse, or attention drop degraded the normal verification routine.
- Use when: the review itself identifies time, fatigue, rushed reading, or a direct input lapse as a material cause.
- Do not use as primary when: the record reveals a specific mechanism that can be trained directly.
- Correction rule: for late-section or time-pressure questions, check only the highest-yield features before marking: subject, comparator, negation, condition boundary, and selected-choice number.

## Status tags

### `INSUFFICIENT_REVIEW_BASIS`

- Korean display name: 리뷰 근거 부족
- Role: data-quality/status tag
- Meaning: the canonical question and grading are available, but the user's reasoning or feedback is insufficient to reconstruct the actual error mechanism.
- Use when: self-review and assistant feedback are absent or too thin to support a mechanism diagnosis.
- Do not promote to final tags.
- Current policy: 2025 추리논증 records with this tag are holdouts for later re-solving and should not contribute to tag frequency, final tag promotion, or active evidence counts.

## Holdout policy

Holdout records remain in `provisional_tags.jsonl` for traceability, but they are excluded from active frequency and promotion analysis. They should be re-solved later, then reviewed again with fresh self-review and canonical-grounded assistant feedback.
