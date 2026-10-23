import asyncio
from functools import partial

from aiokafka import AIOKafkaProducer
from sqlalchemy.dialects.postgresql import insert

from libs.common.db import ComplaintRow, Session
from libs.common.kafka import make_producer, publish, serve
from libs.common.logging import setup_logging
from libs.common.schemas import Complaint, TriagedComplaint


def classify(complaint: Complaint) -> TriagedComplaint:
    # Placeholder until the tier 0 classifier and LLM cascade land.
    return TriagedComplaint(
        **complaint.model_dump(),
        category=complaint.source_category or "Other",
        department=complaint.source_department or "Boston 311",
        urgency="medium",
        duplicate_of=None,
        triage_tier=0,
    )


async def handle(producer: AIOKafkaProducer, complaint: Complaint) -> None:
    triaged = classify(complaint)
    triage_fields = triaged.model_dump(
        include={"category", "department", "urgency", "duplicate_of", "triage_tier"}
    )
    # Triage is the single writer of complaint rows, so downstream services can rely on them.
    stmt = insert(ComplaintRow).values(
        id=complaint.key, **triaged.model_dump(exclude={"schema_version"})
    )
    async with Session.begin() as session:
        await session.execute(stmt.on_conflict_do_update(index_elements=["id"], set_=triage_fields))
    await publish(producer, "complaints.triaged", complaint.key, triaged)


async def main() -> None:
    setup_logging()
    producer = make_producer()
    await producer.start()
    try:
        await serve("complaints.raw", "triage", producer, Complaint, partial(handle, producer))
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
