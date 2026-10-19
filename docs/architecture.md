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
| replay | Yearly CSVs in `data/311/` | Demos, load tests, evals |
| sync | CKAN `datastore_search_sql` on data.boston.gov (no key) | Daily job at 06:00 ET for new records |
| resident | `POST /complaints` | Direct submissions |

- Replay publishes at original `opened_at` spacing divided by `--speed` (1 is real time, 144 replays a day in 10 min).
- Sync queries rows newer than the cursor in `sync_state` from two resources: legacy 2026 (`1a0b420d-99f1-4887-9851-990b2a5a6e17`) and NEW SYSTEM (`254adca6-64ab-4c5c-9fc0-a6da622be185`).
- The two datasets have different structures (legacy case IDs are 12 digits, new ones start with `BCS-`), so each has its own mapper in `services/ingestion/mappers.py`. Read the NEW SYSTEM data dictionary before editing its mapper.
- `source` is `legacy`, `new`, or `resident`.
- Open311 is not used; it needs an approved API key.

## Event Time

Every time window (dedupe 48 h, hotspot 2 h) uses complaint `opened_at`, never wall-clock time, so replay and sync behave identically.

## Triage Dedupe

A complaint is a duplicate when cosine similarity is at least 0.9 with a same-category complaint within 200 m and 48 h.

## Hotspot Algorithm

- Every 60 s of event time, per category, run DBSCAN on complaints opened in the preceding 2 h.
- Haversine metric, `eps = 0.5 km` (pass `0.5 / 6371` radians), `min_samples = 5`.
- A cluster whose centroid is within `eps` of an open same-category incident attaches to it; otherwise it creates a new incident.

## Messaging Rules

- Idempotency key is `{source}:{source_id}`; consumers upsert, so replays are safe.
- Commit the offset only after the DB write succeeds.
- On failure, retry 3 times with backoff (1 s, 4 s, 16 s), then publish to `<topic>.dlq` with the error.
- Every message has `schema_version`; bump it on breaking changes.

## Data Model

| Table | Contents |
|---|---|
| complaints | Normalized fields, `raw_text_enc` (Fernet, key from `PII_KEY`), `text_scrubbed`, triage fields, `embedding vector(384)` |
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
