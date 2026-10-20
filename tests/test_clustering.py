import uuid

from services.hotspot.clustering import find_clusters, match_incident


def test_five_nearby_complaints_form_a_cluster_and_isolated_ones_are_noise() -> None:
    nearby = [(42.3500 + i * 0.0003, -71.0600) for i in range(5)]  # ~33 m apart
    isolated = [(42.3000, -71.1000)]

    assert find_clusters(nearby + isolated) == [[0, 1, 2, 3, 4]]


def test_cluster_attaches_to_open_incident_only_within_eps() -> None:
    near, far = uuid.uuid4(), uuid.uuid4()
    incidents = {near: (42.3530, -71.0600), far: (42.3700, -71.0600)}  # ~0.33 km, ~2.2 km

    assert match_incident((42.3500, -71.0600), incidents) == near
    assert match_incident((42.3900, -71.0600), {near: incidents[near]}) is None
