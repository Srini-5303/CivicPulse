# ADR 0003: DBSCAN for Hotspot Detection

Status: Accepted, 2026-10-17

## Context
Hotspots are groups of nearby same-category complaints in a time window. The number of hotspots is unknown in advance, and most complaints belong to none.

## Decision
DBSCAN per category over a 2 h event-time window, haversine metric, `eps = 0.5 km`, `min_samples = 5`.

## Why
- No cluster count needed up front.
- Isolated complaints are labeled noise instead of forced into a cluster.
- The parameters read as a plain rule staff can check: "5 complaints within 0.5 km."
- Fast at this size, a few hundred points per category window.

## Alternatives Rejected
- k-means: needs the cluster count and assigns every complaint to a cluster.
- HDBSCAN: handles varying density better, but its parameters are harder to explain.
- Geohash cell counts: simplest, but splits real clusters across cell boundaries.
- LLM clustering: costly, slow, and non-deterministic for a geometric problem.

## Consequences
- One `eps` does not adapt to density, so dense downtown streets may over-cluster while outer neighborhoods under-cluster.
- Re-running every minute can shift cluster membership, so incident identity depends on centroid matching.

## Revisit When
The hotspot eval shows density differences hurting detection; switch to HDBSCAN.
