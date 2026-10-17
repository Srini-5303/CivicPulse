# Agents

## Incident Graph

`investigate -> retrieve -> draft -> redact -> assign_tier -> (auto_approve | human_review) -> publish`

- `human_review` calls `interrupt()`; state is checkpointed with `PostgresSaver`, `thread_id` = draft ID.
- The approval service resumes a thread with `POST /threads/{id}/resume` and the decision.
- `reject` ends the graph with the reason recorded; `edit` sends the edited text back through `redact` before publishing.
- Acknowledgments for non-duplicate complaints skip the graph: fixed template with reference ID, no LLM.

## State

`IncidentState` (Pydantic): incident, complaint IDs with `text_scrubbed`, tool results, retrieved chunks, draft, redaction result, tier, decision.

## Tools (MCP servers in `mcp/`)

| Server | Tools | Limits |
|---|---|---|
| weather | `get_forecast(lat, lon)`, `get_alerts(lat, lon)` | api.weather.gov, requires a `User-Agent` header |
| history | `query_history(sql)` | `history_ro` role on view `v_complaints_public` only, 5 s timeout, 200 rows max |
| schedule | `planned_work(lat, lon, radius_km)` | Synthetic data in `data/planned_work.csv` |

- Max 6 tool calls per run.
- Tool errors return as tool results the agent can reason about, not exceptions.

## RAG

- Corpus in `data/kb/`: department procedures, service commitments, communication guidelines, public records rules.
- Chunks of about 500 tokens with 50 overlap, stored in `kb_chunks`.
- Hybrid retrieval: pgvector cosine plus Postgres full-text, merged with reciprocal rank fusion (k = 60), top 5.
- Every commitment in a draft (dates, timelines, actions) must cite a chunk ID. An uncited commitment fails validation, regenerates once, then goes to human review.

## Prompts

- One file per node in `services/agents/prompts/<node>.md`, loaded at startup.
- Complaint text goes inside `<complaint>` tags and is treated as data, never instructions.
