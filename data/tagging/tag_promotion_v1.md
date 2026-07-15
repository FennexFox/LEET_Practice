# Tag Promotion v1

## Decisions

Promote the following provisional mechanism tags to final tag candidates:

1. `SCOPE_CONDITION_MISAPPLICATION`
2. `CONCEPT_LAYER_CONFUSION`
3. `ARGUMENT_STRUCTURE_INCOMPLETE`
4. `FORMAL_CONDITION_ERROR`
5. `GLOBAL_CONSTRAINT_DROPPED`
6. `TABLE_DIAGRAM_ENCODING_ERROR`
7. `RELATION_DIRECTION_REVERSAL`
8. `TEXTUAL_REDEFINITION_MISSED`
9. `UNWARRANTED_ASSUMPTION_ADDED`

Keep the following outside the final mechanism set:

- `CHOICE_VERIFICATION_FAILURE`: supporting tag, usually secondary.
- `TIME_PRESSURE_OR_ATTENTION_LAPSE`: operational modifier.
- `INSUFFICIENT_REVIEW_BASIS`: data-quality/status tag; not an error mechanism.

Keep under observation:

- `ROLE_ATTRIBUTION_ERROR`: clear but lower-frequency provisional mechanism. Revisit after representative-case review.

## Assignment corrections applied

| Review file | Previous assignment | Revised assignment | Reason |
| --- | --- | --- | --- |
| `data/reviews/2020 추리논증 홀수형/q39.review.json` | primary `RELATION_DIRECTION_REVERSAL`; secondary `TABLE_DIAGRAM_ENCODING_ERROR` | primary `TABLE_DIAGRAM_ENCODING_ERROR`; secondary `TEXTUAL_REDEFINITION_MISSED`, `RELATION_DIRECTION_REVERSAL` | The core failure was not just direction reversal; the user failed to re-encode the exchange-resin name into the passage-defined charge table. |
| `data/reviews/2026 언어이해 홀수형/q12.review.json` | primary `RELATION_DIRECTION_REVERSAL`; secondary `TEXTUAL_REDEFINITION_MISSED` | primary `TEXTUAL_REDEFINITION_MISSED`; secondary `RELATION_DIRECTION_REVERSAL` | The core failure was treating the passage's institution-change wording, especially 보완/도입, as 대체. |
| `data/reviews/2026 추리논증 홀수형/q29.review.json` | primary `ARGUMENT_STRUCTURE_INCOMPLETE`; no secondary | primary `ARGUMENT_STRUCTURE_INCOMPLETE`; secondary `UNWARRANTED_ASSUMPTION_ADDED` | A weakening of theory A was treated as an automatic strengthening of theory B by adding an unsupported mutually exclusive relation. |

## Active primary frequency after 2024 tagging

The 17 active 2024 review records fit the existing taxonomy without a new tag. There are currently no holdout records; future holdouts remain excluded.

| Tag | Active primary count |
| --- | ---: |
| `SCOPE_CONDITION_MISAPPLICATION` | 22 |
| `CONCEPT_LAYER_CONFUSION` | 20 |
| `ARGUMENT_STRUCTURE_INCOMPLETE` | 9 |
| `FORMAL_CONDITION_ERROR` | 10 |
| `CHOICE_VERIFICATION_FAILURE` | 5 |
| `GLOBAL_CONSTRAINT_DROPPED` | 11 |
| `TABLE_DIAGRAM_ENCODING_ERROR` | 13 |
| `ROLE_ATTRIBUTION_ERROR` | 4 |
| `RELATION_DIRECTION_REVERSAL` | 4 |
| `TEXTUAL_REDEFINITION_MISSED` | 6 |
| `UNWARRANTED_ASSUMPTION_ADDED` | 6 |
| `TIME_PRESSURE_OR_ATTENTION_LAPSE` | 2 |

## Notes for final-tag application

- Final tags should be written only after representative-case confirmation or user acceptance.
- Supporting/status tags can remain in the tagging layer but should not be copied into `final_error_tags` as primary mechanisms.
- If a record's primary provisional tag is a supporting/status tag, review whether a deeper final mechanism is recoverable. If not, leave the record pending rather than forcing a mechanism label.
