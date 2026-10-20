import math
from collections import defaultdict
from uuid import UUID

import numpy as np
from sklearn.cluster import DBSCAN

EARTH_RADIUS_KM = 6371.0
EPS_KM = 0.5
MIN_SAMPLES = 5

Point = tuple[float, float]


def find_clusters(points: list[Point]) -> list[list[int]]:
    """Return clusters as lists of indexes into `points`; noise points are dropped."""
    if len(points) < MIN_SAMPLES:
        return []
    labels = (
        DBSCAN(eps=EPS_KM / EARTH_RADIUS_KM, min_samples=MIN_SAMPLES, metric="haversine")
        .fit(np.radians(points))
        .labels_
    )
    clusters: dict[int, list[int]] = defaultdict(list)
    for index, label in enumerate(labels):
        if label != -1:
            clusters[label].append(index)
    return list(clusters.values())


def centroid(points: list[Point]) -> Point:
    # A plain mean is accurate enough over a city-sized area.
    return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))


def haversine_km(a: Point, b: Point) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def match_incident(center: Point, open_incidents: dict[UUID, Point]) -> UUID | None:
    """Nearest open incident whose centroid is within eps, if any."""
    distances = {iid: haversine_km(center, c) for iid, c in open_incidents.items()}
    within = {iid: d for iid, d in distances.items() if d <= EPS_KM}
    return min(within, key=within.__getitem__) if within else None
