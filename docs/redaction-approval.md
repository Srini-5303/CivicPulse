# Redaction and Approval

## Redaction Service

`POST /redact` takes draft text and incident ID. It returns redacted text and spans `{start, end, entity_type, action, reason_code, confidence, layer}`, where `action` is `redact` or `generalize`.

- `redact` replaces the span with `[REDACTED: <entity_type>]`.
- `generalize` applies to street addresses in all outgoing text: the house number becomes its block ("42 Elm St" becomes "the unit block of Elm St", "245 Elm St" becomes "the 200 block of Elm St"). Intersections stay as written.
- Words matching a street name in `data/boston_streets.csv` (built from city street centerline data) are never tagged `PERSON`, so "Washington St" is not redacted.

Layers, in order:
1. Presidio and regex: `PERSON`, `PHONE_NUMBER`, `EMAIL_ADDRESS`, street addresses (custom recognizer, generalized), staff names from `data/staff.csv`.
2. LLM review (tier 2): contextual identifiers ("the blue house on the corner"), internal notes, staff attributions.
3. Policy check with RAG over public records rules: withholds critical infrastructure details and anything the rules mark non-disclosable.

Fail closed: any error or a 10 s timeout returns 503, and the graph sends the draft to review flagged `redaction_failed`. It is never published.

## Risk Tiers

| Tier | Condition | Path |
|---|---|---|
| auto | Template acknowledgment | Publish; 5% sampled into the review queue after sending |
| review | Any LLM draft | Human approval required |
| priority | `redaction_failed`, any layer 2 or 3 redaction, or span confidence < 0.8 | Top of the review queue |

## Approval Service

- FastAPI with Jinja and HTMX. Lists pending drafts, priority first, then oldest first.
- Shows the draft, the redacted version with highlighted spans and reasons, and cited chunks.
- Decisions: approve, edit, reject with reason.
- Drafts pending over 4 h escalate to the `supervisor` role.
- Every decision writes `approvals` and `audit_log`. Reviewer edits export nightly to `evals/datasets/redaction_feedback.jsonl`.
