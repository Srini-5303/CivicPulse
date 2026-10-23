import random

import httpx
from redis.asyncio import Redis

from libs.common.config import settings
from libs.common.schemas import Complaint
from services.ingestion.api import app
from tests.fakes import FakeProducer

BODY = {"text": "Pothole outside my door", "lat": 42.35, "lon": -71.06}


def _client(producer: FakeProducer) -> httpx.AsyncClient:
    # State is set by hand because ASGITransport does not run the lifespan (Kafka, Presidio).
    app.state.producer = producer
    app.state.redis = Redis.from_url(settings.redis_url)
    app.state.protect = lambda text: ("enc", "scrubbed")
    # A random client IP keeps runs within the same minute from sharing a rate-limit window.
    ip = f"10.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"
    transport = httpx.ASGITransport(app=app, client=(ip, 1234))
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_resident_complaint_is_published_scrubbed() -> None:
    producer = FakeProducer()
    async with _client(producer) as client:
        response = await client.post("/complaints", json=BODY)

    assert response.status_code == 202
    [(topic, value)] = producer.sent
    complaint = Complaint.model_validate_json(value)
    assert topic == "complaints.raw"
    assert response.json() == {"reference_id": complaint.key}
    assert (complaint.source, complaint.text_scrubbed) == ("resident", "scrubbed")


async def test_eleventh_complaint_in_a_minute_is_rate_limited() -> None:
    async with _client(FakeProducer()) as client:
        statuses = [(await client.post("/complaints", json=BODY)).status_code for _ in range(11)]

    assert statuses == [202] * 10 + [429]
