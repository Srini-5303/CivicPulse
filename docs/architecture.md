# Architecture

Kafka carries the high-volume complaint stream. LangGraph runs the per-incident workflow. Services use HTTP only where a synchronous answer is needed.

## Services

| Service | Input | Output | Job |
|---|---|---|---|
| ingestion | Replay, daily sync, `POST /complaints` (see Ingestion Modes) | `complaints.raw` | Normalize to `Complaint`, encrypt raw text, scrub PII into `text_scrubbed` |
| triage | `complaints.raw` | `complaints.triaged` | Category, department, urgency, embedding, `duplicate_of` |
| hotspot | `complaints.triaged` | `incidents.detected` | Cluster complaints into incidents |
| agents | `incidents.detected`, `complaints.triaged` | `responses.approved` | LangGraph workflow (see `agents.md`) |
| redaction | HTTP `POST /redact` | | Called by agents (see `redaction-approval.md`) |
| approval | Pending drafts in Postgres | HTTP resume call to agents | Staff review UI and API |
| notifier | `responses.approved` | Email (dev: `outbox` table) | Send, then write audit record |

## Ingestion Modes

All modes publish the same `Complaint` to `complaints.raw`; downstream services cannot tell them apart.

| Mode | Source | Used for |
|---|---|---|
| replay | Yearly CSVs in `data/311/` (`legacy_*.csv`, `new_*.csv`; git-ignored) | Demos, load tests, evals |
| sync | CKAN `datastore_search_sql` on data.boston.gov (no key) | Daily job at 06:00 ET for new records |
| resident | `POST /complaints` | Direct submissions |

- Replay publishes at original `opened_at` spacing divided by `--speed` (1 is real time, 144 replays a day in 10 min). `--from`/`--to` are Boston local dates.
- Sync queries rows newer than the cursor in `sync_state` from two resources: legacy 2026 (`1a0b420d-99f1-4887-9851-990b2a5a6e17`) and NEW SYSTEM (`254adca6-64ab-4c5c-9fc0-a6da622be185`). It pages 1,000 rows at a time with `>=` the cursor, so rows tied at a page boundary are re-read rather than skipped, and saves the cursor after each page is published. With no cursor it starts one day back; history comes from replay. A failed run leaves the cursor at the last published page, and the next run resumes there. `python -m services.ingestion.sync --once` runs it immediately.
- Both systems are live: the city moves services from legacy to NEW SYSTEM one at a time (for example missed trash moved in June 2026), so the two hold different cases, not copies.
- Legacy timestamps are Boston local time without an offset; NEW SYSTEM timestamps are UTC.
- The two datasets have different structures (legacy case IDs are 12 digits, new ones start with `BCS-`), so each has its own mapper in `services/ingestion/mappers.py`. Read the NEW SYSTEM data dictionary before editing its mapper.
- `source` is `legacy`, `new`, or `resident`.
- Open311 is not used; it needs an approved API key.
- Neither system has a resident description field: legacy uses `case_title` as the complaint text and NEW SYSTEM uses `service_name` (or `case_topic` when it is blank). Only resident submissions carry free text.
- Legacy rows at exactly (42.3594, -71.0587), or with `location_street_name` `1 City Hall Plz` or `100 City Hall Plz`, are City Hall placeholders for a missing location, as are NEW SYSTEM rows at street number `1` on `City Hall Plz`: the mappers set `lat`/`lon` to null, so they are triaged but skipped by dedupe and hotspot. Intersections and `City Hall Ave` addresses are real locations.
- `POST /complaints` takes `text` and `lat`/`lon` (required, no geocoder, limited to a Boston bounding box), is rate limited to 10 per minute per IP in Redis, and returns the complaint key (`resident:<id>`) as the reference ID.

## Categories

- The canonical categories are NEW SYSTEM `service_name`s, since that is where the city is moving, plus legacy types with no NEW SYSTEM equivalent yet.
- `data/categories.csv` maps every legacy `type` to a canonical category and department; review it when the city moves another service. A legacy type missing from it keeps its own name and is logged.
- NEW SYSTEM rows use their own `service_name` and `assigned_department`.
- These become `source_category` and `source_department` on `Complaint`; resident submissions have none, so triage must classify them.

## PII Scrub

- Ingestion scrubs every text with `libs/common/pii.py` (shared with redaction): Presidio `PERSON`, `PHONE_NUMBER`, and `EMAIL_ADDRESS` at score 0.3 or more become `[REDACTED: <type>]`, and house numbers become their block ("the 200 block of Elm St").
- A `PERSON` match made only of words from category names is kept, because title-case categories ("Missed Trash: District 07") look like names to the model. Parks named after people ("Franklin Park") are still over-scrubbed until the street and place allowlist lands with redaction.

## Event Time

Every time window (dedupe 48 h, hotspot 2 h) uses complaint `opened_at`, never wall-clock time, so replay and sync behave identically.

## Triage Dedupe

A complaint is a duplicate when cosine similarity is at least 0.9 with a same-category complaint within 200 m and 48 h.

## Hotspot Algorithm

- Every 60 s of event time, per category, run DBSCAN on complaints opened in the preceding 2 h.
- Haversine metric, `eps = 0.5 km` (pass `0.5 / 6371` radians), `min_samples = 5`.
- A cluster whose centroid is within `eps` of an open same-category incident attaches to it; otherwise it creates a new incident.
- An open incident closes after 24 h of event time with no new linked complaint. Half of nearby same-type repeat reports in early 2025 came 6 h or more apart, mostly across the overnight lull, so a shorter limit splits one issue into two; 24 h keeps 70% of repeats within a week in the same incident.
- Only new incidents are published to `incidents.detected`; attaching complaints only adds `incident_complaints` links.
- A jump in event time of several steps (such as a daily sync batch) runs detection once, not once per step.
- A jump back past the whole window (a replay of older data after newer data) restarts event time instead of skipping the older complaints. Replay and live sync should not run into the same pipeline at the same time.

## Messaging Rules

- Idempotency key is `{source}:{source_id}`; consumers upsert, so replays are safe.
- Triage is the only writer of `complaints` rows, upserting before it publishes, so later stages can read them.
- IDs derived from a message (incident, draft, outbox) are UUIDv5 of its inputs, so a redelivered message cannot create a second row.
- Commit the offset only after the DB write succeeds.
- On failure, retry 3 times with backoff (1 s, 4 s, 16 s), then publish to `<topic>.dlq` with the error.
- Every message has `schema_version`; bump it on breaking changes.

## Data Model

| Table | Contents |
|---|---|
| complaints | Normalized fields, `source_category`/`source_department`, `raw_text_enc` (Fernet, key from `PII_KEY`), `text_scrubbed`, triage fields, `embedding vector(384)` |
| incidents | Category, centroid, status, `detected_at` |
| incident_complaints | Incident to complaint links |
| drafts | Draft ID (also the LangGraph `thread_id`), draft text, redacted text, spans, citations, risk tier |
| approvals | Draft ID, reviewer, decision, edited text, reason |
| audit_log | Append-only record of every decision |
| kb_chunks | RAG chunks: source, text, embedding, `tsvector` |
| sync_state | Last synced `opened_at` per CKAN resource |
| outbox | Dev stand-in for email: recipient, subject, body per draft |

Embeddings use local `all-MiniLM-L6-v2` (384 dimensions).

`v_complaints_public` exposes complaint IDs, source, time, location, and triage fields, but no text or embeddings, because the history tool's results reach an LLM.
