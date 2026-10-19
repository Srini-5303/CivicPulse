from datetime import UTC, datetime
from types import SimpleNamespace

from libs.common.kafka import run_consumer
from libs.common.schemas import Complaint, DeadLetter

COMPLAINT = Complaint(
    source="legacy",
    source_id="101",
    opened_at=datetime(2025, 1, 1, tzinfo=UTC),
    lat=42.35,
    lon=-71.06,
    category_raw="Pothole",
    raw_text_enc="enc",
    text_scrubbed="pothole on [ADDRESS]",
)


class FakeConsumer:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.records = [
            SimpleNamespace(
                topic="complaints.raw",
                partition=0,
                offset=7,
                key=b"legacy:101",
                value=COMPLAINT.model_dump_json().encode(),
            )
        ]

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for record in self.records:
            yield record

    async def commit(self, offsets: dict) -> None:
        self.events.append(f"commit:{next(iter(offsets.values()))}")


class FakeProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes]] = []

    async def send_and_wait(self, topic: str, value: bytes, key: bytes | None = None) -> None:
        self.sent.append((topic, value))


async def no_sleep(_: float) -> None:
    pass


async def test_commits_offset_only_after_handler_succeeds() -> None:
    events: list[str] = []

    async def handler(c: Complaint) -> None:
        events.append(f"handled:{c.key}")

    await run_consumer(FakeConsumer(events), FakeProducer(), Complaint, handler, no_sleep)

    assert events == ["handled:legacy:101", "commit:8"]


async def test_retries_three_times_then_sends_to_dlq() -> None:
    events: list[str] = []
    sleeps: list[float] = []
    producer = FakeProducer()

    async def handler(_: Complaint) -> None:
        events.append("attempt")
        raise RuntimeError("db down")

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    await run_consumer(FakeConsumer(events), producer, Complaint, handler, record_sleep)

    assert sleeps == [1.0, 4.0, 16.0]
    assert events == ["attempt"] * 4 + ["commit:8"]
    [(topic, value)] = producer.sent
    assert topic == "complaints.raw.dlq"
    assert DeadLetter.model_validate_json(value).error_type == "RuntimeError"
