# ADR 0004: LangGraph for the Incident Workflow

Status: Accepted, 2026-10-17

## Context
The incident workflow is mostly fixed steps with one tool-using agent. It must pause for human approval for hours and resume correctly after restarts.

## Decision
LangGraph with the `PostgresSaver` checkpointer.

## Why
- Explicit state machine: routing between nodes is deterministic, and only `investigate` acts autonomously.
- Built-in `interrupt()` and resume for human approval.
- Durable checkpoints in the Postgres instance already running.
- Native Langfuse tracing.

## Alternatives Rejected
- Plain Python with a state table: viable, but reimplements checkpointing and resume.
- CrewAI, AutoGen: built around conversing role-based agents, a poor fit for a mostly fixed pipeline.
- Temporal: the strongest durable execution, but another server on a memory-limited free VM.

## Consequences
- Framework lock-in and frequent API changes; pin the version.
- Changing graph structure can break resume for paused threads.

## Revisit When
The workflow needs long-running timers or retries beyond what checkpoints handle; consider Temporal.
