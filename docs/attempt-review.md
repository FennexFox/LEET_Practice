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

Open the local browser workbench:

```powershell
leet-practice attempt-review serve attempt-001
```

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
