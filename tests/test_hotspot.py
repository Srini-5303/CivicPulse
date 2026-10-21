import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from libs.common.db import ComplaintRow, IncidentComplaintRow, IncidentRow, Session
from services.hotspot.main import CLOSE_AFTER, detect
from tests.fakes import FakeProducer

T0 = datetime(2025, 1, 2, 9, 0, tzinfo=UTC)


async def _incident_with_last_complaint_at(opened_at: datetime) -> uuid.UUID:
    incident_id = uuid.uuid4()
    complaint_id = f"legacy:{incident_id}"
    async with Session.begin() as session:
        session.add(
            ComplaintRow(
                id=complaint_id,
                source="legacy",
                source_id=str(incident_id),
                opened_at=opened_at,
                lat=42.35,
                lon=-71.06,
                category_raw="Closure Test",
                raw_text_enc="enc",
                text_scrubbed="",
                category="Closure Test",
            )
        )
        session.add(
            IncidentRow(
                id=incident_id,
                category="Closure Test",
                centroid_lat=42.35,
                centroid_lon=-71.06,
                status="open",
                detected_at=opened_at,
            )
        )
        await session.flush()
        session.add(IncidentComplaintRow(incident_id=incident_id, complaint_id=complaint_id))
    return incident_id


async def test_incident_closes_after_a_quiet_day_of_event_time() -> None:
    quiet = await _incident_with_last_complaint_at(T0)
    active = await _incident_with_last_complaint_at(T0 + timedelta(hours=23))

    await detect(FakeProducer(), T0 + CLOSE_AFTER + timedelta(minutes=1))

    async with Session() as session:
        statuses = dict((await session.execute(select(IncidentRow.id, IncidentRow.status))).all())
    assert statuses[quiet] == "closed"
    assert statuses[active] == "open"
