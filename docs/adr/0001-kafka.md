# ADR 0001: Kafka (Redpanda) for the Complaint Stream

Status: Accepted, 2026-10-17

## Context
Complaints arrive from replay, daily sync, and direct submissions, then pass through ingestion, triage, hotspot, and agents. Boston's volume is low (about 274,000 requests in 2021, roughly 750 per day), so volume alone does not justify Kafka.

## Decision
Use the Kafka API through Redpanda, which runs as a single binary with lower memory use than Apache Kafka.

## Why
- Replay: historical data flows through the same pipeline at any speed, and resetting consumer offsets reprocesses everything after a model or prompt change.
- Isolation: a slow LLM stage never blocks ingestion, and each consumer fails and scales on its own.
- The topic log is a durable record of every input for debugging and evals.

## Alternatives Rejected
- Postgres queue table (`FOR UPDATE SKIP LOCKED`): handles Boston's volume and is simpler, but has no native replay or independent consumers per message. It is the first choice if operating cost matters more than replay.
- Redis Streams: supports consumer groups and replay, but retention is bounded by memory.
- RabbitMQ: deletes messages on acknowledgment, so no replay.

## Consequences
- One more container to run and monitor.
- At-least-once delivery requires idempotent consumers.
- The load test must show the pipeline at 100x Boston volume to back the isolation claim.

## Revisit When
Replay is no longer used, or the single VM runs short on memory.
