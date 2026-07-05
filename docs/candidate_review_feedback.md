# Candidate Review Feedback System

v0.6.4 adds a review feedback layer for cleanup candidates.

The goal is simple: FLO can now collect human decisions about candidate cleanup marks without changing Paint Studio geometry. This keeps candidate planning grounded in review evidence before any future cleanup logic exists.

## Purpose

Candidate plans are only suggestions. They identify shapes that might be removable, protected, or worth a closer look.

The feedback system records human review decisions for those candidates:

- `accepted`: the candidate looks reasonable for future cleanup.
- `rejected`: the candidate should not be cleaned up.
- `unsure`: the candidate needs more review.
- `protected`: the candidate should be explicitly protected from cleanup.

## Create Feedback

For a prepared case folder:

```bash
python scripts/create_candidate_feedback_template.py --case cases/case_0001
```

This reads:

```text
cases/case_0001/optimization_plan.json
```

and writes:

```text
cases/case_0001/candidate_review/candidate_feedback.json
cases/case_0001/candidate_review/candidate_feedback.csv
```

Every candidate starts as `unsure`.

## Update One Candidate

```bash
python scripts/update_candidate_feedback.py --feedback cases/case_0001/candidate_review/candidate_feedback.json --change-id C0001 --status accepted --note "Looks safe after visual review"
```

The update script rewrites only the feedback JSON and feedback CSV. It does not touch source geometry, optimized geometry, or Paint Studio files.

## Validate Feedback

```bash
python scripts/validate_candidate_feedback.py --feedback cases/case_0001/candidate_review/candidate_feedback.json --plan cases/case_0001/optimization_plan.json
```

Validation checks that:

- required feedback fields exist
- statuses are valid
- counts match the feedback items
- feedback `change_id` values exist in the plan
- feedback `shape_uid` values still match the plan

## Summarize Feedback

```bash
python scripts/summarize_candidate_feedback.py --feedback cases/case_0001/candidate_review/candidate_feedback.json
```

The summary prints total reviewed items and counts for each status.

## Review Visualization Integration

When `candidate_feedback.json` exists in the candidate review folder, `render_candidate_review.py` reads it automatically:

```bash
python scripts/render_candidate_review.py --case cases/case_0001 --top-n 50
```

Contact sheet labels include each candidate's feedback status. The review index includes feedback counts.

## Read-Only Guarantee

This system is diagnostic and review-only.

It does not:

- delete shapes
- update shapes
- create replacement shapes
- write optimized geometry
- modify Paint Studio source
- touch injection logic

Future cleanup versions can use accepted, rejected, unsure, and protected decisions as evidence. v0.6.4 only records the decisions.
