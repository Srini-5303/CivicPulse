# LLM Gateway

`libs/common/llm.py` wraps LiteLLM. Model names live only there as constants; check current free-tier names before changing them.

## Routing (cascade)

| Tier | Model | Used for |
|---|---|---|
| 0 | Logistic regression on TF-IDF (`models/triage_clf.joblib`), no LLM | Triage first pass |
| 1 | Groq `llama-3.1-8b-instant` | Triage when tier 0 confidence < 0.8 |
| 2 | Groq `llama-3.3-70b-versatile` | Triage escalations, investigation, drafting, redaction review |

- Escalate tier 1 to tier 2 when output fails validation or reported confidence < 0.7.
- Train tier 0 on historical Boston 311 labels with `uv run python -m services.triage.train`.

## Fallback

- Order per call: Groq, then Gemini Flash, then local Ollama `llama3.1:8b`.
- Timeout 20 s. Circuit breaker opens after 5 consecutive provider failures for 60 s.

## Caching

Redis semantic cache for triage only: reuse a result when embedding similarity is at least 0.95, TTL 24 h. Never cache drafts or redaction.

## Structured Output

Every call declares a Pydantic response model. On validation failure, retry once with the error in the prompt, then raise.

## Tokens and Context

- Each call is a Langfuse generation tagged `service`, `task`, `tier`, with tokens, cost, and latency.
- Count prompt tokens before sending. Above 70% of the model's context window, drop the lowest-ranked RAG chunks first, then the oldest tool results.
- Export Prometheus counters `llm_tokens_total` and `llm_cost_usd_total` labeled by tier and task.
