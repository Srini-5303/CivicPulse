from datetime import UTC, datetime, timedelta

from libs.common.db import Session, SyncStateRow
from libs.common.schemas import Complaint
from services.ingestion.sync import RESOURCES, seconds_until_next_run, sync_resource
from tests.fakes import FakeProducer
from tests.test_mappers import NEW

NEW_SYSTEM = RESOURCES[1]
T0 = datetime(2026, 7, 2, 6, 0, tzinfo=UTC)


async def test_sync_pages_through_new_rows_and_saves_cursor() -> None:
    rows = [
        {**NEW, "case_id": f"BCS-{i}", "open_date": (T0 + timedelta(minutes=i)).isoformat()}
        for i in range(5)
    ]
    cursors: list[datetime] = []

    async def fetch(resource, cursor: datetime, limit: int) -> list[dict[str, str]]:
        cursors.append(cursor)
        return [r for r in rows if datetime.fromisoformat(r["open_date"]) >= cursor][:limit]

    producer = FakeProducer()
    await sync_resource(
        NEW_SYSTEM, fetch, producer, lambda t: ("enc", t), now=T0 + timedelta(hours=1), page_size=2
    )

    # The first cursor is a day back; each later page re-reads the newest row seen so far.
    assert cursors[0] == T0 + timedelta(hours=1) - timedelta(days=1)
    assert cursors[1:] == [T0 + timedelta(minutes=i) for i in range(1, 5)]
    published = {Complaint.model_validate_json(v).key for _, v in producer.sent}
    assert published == {f"new:BCS-{i}" for i in range(5)}
    async with Session() as session:
        state = await session.get(SyncStateRow, NEW_SYSTEM.id)
    assert state.last_opened_at == T0 + timedelta(minutes=4)


def test_daily_run_waits_until_six_am_boston_time() -> None:
    five_am_edt = datetime(2026, 7, 2, 9, 0, tzinfo=UTC)
    seven_am_edt = datetime(2026, 7, 2, 11, 0, tzinfo=UTC)

    assert seconds_until_next_run(five_am_edt) == 3600
    assert seconds_until_next_run(seven_am_edt) == 23 * 3600
