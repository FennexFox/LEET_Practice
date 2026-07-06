# Attempt review workflow

Attempt review is separate from OCR verification. OCR verification promotes
question text into canonical data; attempt review records what the user answered,
why they answered that way, and how assistant feedback was resolved.

## Data flow

```text
data/attempts/<attempt_id>.json
-> data/reviews/<attempt_id>/qXXX.review.json
-> data/reviews/<attempt_id>/feedback_request.json
-> assistant_feedback.json
-> qXXX.review.json assistant_feedback
-> user_resolution
```

## Commands

Create an attempt record:

```powershell
leet-practice attempt-review create attempt-001 leet-2026-reasoning-even --answers "22542 52323"
```

Grade the attempt and create review files for wrong questions:

```powershell
leet-practice attempt-review grade attempt-001
```

Fix answer-entry mistakes by question number:

```powershell
leet-practice attempt-review regrade attempt-001 --answer 12=5 --answer 27=3
```

`regrade` updates only the listed selected answers. If a previously wrong
question becomes correct, its review file is moved under
`data/reviews/<attempt_id>/archived/`. If a question remains wrong, existing
user self-review is preserved. Assistant feedback is cleared when the grading
for that question changes, because the previous diagnosis may no longer apply.

Open the local browser workbench:

```powershell
leet-practice attempt-review serve attempt-001
```

When `questions.jsonl` links a question to `passages.jsonl` with `passage_id`,
the workbench shows the passage above the question text. Feedback export includes
that passage text so assistant feedback can use the same evidence the user sees.

Export a local bundle for assistant feedback:

```powershell
leet-practice attempt-review feedback-export attempt-001
```

Import assistant feedback produced from that bundle:

```powershell
leet-practice attempt-review feedback-import attempt-001 --file .\assistant_feedback.json
```

## Answer source

Grading prefers `data/canonical/<exam_id>/answer_key.json`. If that file does
not exist, it falls back to `data/canonical/<exam_id>/questions.jsonl` fields
such as `correct_answer` or `correct_choice`. If both sources exist and disagree
for the same question, grading fails instead of guessing.

## Separation rule

User self-review fields are the user's raw reasoning evidence. Assistant feedback
is imported into `assistant_feedback` and may include `provisional_error_tags`,
but those tags are not final until the user records a resolution.
