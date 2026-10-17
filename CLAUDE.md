# CivicPulse

Event-driven multi-agent system that triages Boston 311 complaints, detects incident hotspots, and drafts public responses that are redacted and human-approved before sending.

## 1. Think Before Coding

Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

- Touch only what the task requires; don't refactor, rename, or reformat neighboring code.
- Match the existing style, even if you'd do it differently.
- Remove imports and functions your change made unused; mention pre-existing dead code instead of deleting it.
- Every changed line must trace back to the request.

## Project Rules

- Python 3.12, type hints everywhere, async I/O.
- Cross-service messages are Pydantic models in `libs/common/schemas.py`; never pass raw dicts.
- All LLM calls go through `libs/common/llm.py`; never import a provider SDK elsewhere.
- LLMs only receive scrubbed complaint text (`text_scrubbed`), because free-tier providers may retain prompts.
- Never log complaint text or personal data; log IDs.
- No new dependency without asking.
- Comments explain why, never what.
- One test per new behavior; don't test framework or library code.
- Schema changes only through Alembic migrations.

## Stack

FastAPI, LangGraph, LiteLLM, Pydantic v2, SQLAlchemy 2 + Alembic, Postgres 16 + pgvector, Redis, Redpanda (Kafka API) via aiokafka, Presidio, scikit-learn, sentence-transformers, Langfuse, Prometheus + Grafana, pytest, ruff, uv.

## Layout

```
services/{ingestion,triage,hotspot,agents,redaction,approval,notifier}/
libs/common/   schemas, kafka, db, llm gateway, logging
mcp/           MCP tool servers
evals/         suites, datasets, baseline
data/          RAG corpus and synthetic data
infra/         compose overrides, Caddy, Grafana
migrations/    Alembic
docs/          detailed specs
```

## Commands

```
docker compose up -d
uv sync
uv run alembic upgrade head
uv run pytest
uv run ruff check --fix . && uv run ruff format .
uv run python -m evals.run <suite>
uv run python -m services.ingestion.replay --from 2025-01-01 --to 2025-01-07 --speed 144
```

## Docs

Read only the doc for the part you are changing. If code and a doc disagree, ask which is right. When a decision in a doc changes, update the doc in the same change.

| Working on | Read |
|---|---|
| Ingestion, services, Kafka topics, retries, hotspot algorithm, DB schema | `docs/architecture.md` |
| LangGraph workflow, MCP tools, RAG, prompts | `docs/agents.md` |
| Any LLM call, routing, fallback, caching, token tracking | `docs/llm.md` |
| Redaction, risk tiers, approval UI | `docs/redaction-approval.md` |
| Eval suites and CI gates | `docs/evals.md` |
| Docker, CI/CD, deploy, auth, secrets, metrics, alerts | `docs/ops.md` |
| Why Kafka, MCP, DBSCAN, or LangGraph was chosen, or a change to one | `docs/adr/` |
