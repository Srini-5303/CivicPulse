# Hosting, Security, Monitoring

## Environments

- Local: `docker compose up -d` runs Redpanda, Postgres, Redis, Prometheus, Grafana, Ollama, and all services. Tracing uses Langfuse Cloud free tier.
- Prod: one Oracle Cloud Always Free Ampere VM (ARM64) running the same compose file plus `infra/compose.prod.yml`, Caddy for TLS, Cloudflare DNS in front.
- CI (GitHub Actions): ruff, pytest, eval slices, pip-audit, build arm64 images to GHCR. Deploy on tag over SSH with `docker compose pull && docker compose up -d`.

## Security

- Secrets: `.env` locally (git-ignored, `.env.example` committed). Prod secrets live in GitHub Actions secrets and are written to the server on deploy.
- Auth: approval UI and API require a JWT with role `staff` or `supervisor`. Public `POST /complaints` is unauthenticated but rate limited to 10 per minute per IP in Redis.
- Prompt injection: the only side effect, publishing, happens after the approval gate.
- DB roles: `app` has no UPDATE or DELETE on `audit_log`; `history_ro` has SELECT on `v_complaints_public` only.
- Only Caddy ports 80 and 443 are exposed. Postgres, Redis, and Redpanda stay on the internal Docker network.

## Monitoring

- Every service exposes `/metrics` and `/health`.
- Metrics: messages processed and failed per topic, consumer lag, stage latency p50 and p95, DLQ depth, approval queue size and oldest age, redaction failures.
- Alerts: consumer lag > 1,000, DLQ depth > 0, oldest approval past its SLA, any redaction failure.
- Dashboards and alert rules live in `infra/grafana/`.
- Logs: JSON to stdout with `trace_id`, `complaint_id`, `incident_id`.
