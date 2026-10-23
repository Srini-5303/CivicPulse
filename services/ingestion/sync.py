import argparse
import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any

import httpx
from aiokafka import AIOKafkaProducer
from sqlalchemy.dialects.postgresql import insert

from libs.common.db import Session, SyncStateRow
from libs.common.kafka import make_producer, publish
from libs.common.logging import setup_logging
from libs.common.schemas import Complaint
from services.ingestion.mappers import (
    BOSTON_TZ,
    Protect,
    legacy_opened_at,
    map_legacy,
    map_new,
    new_opened_at,
)
from services.ingestion.privacy import make_protect

log = logging.getLogger(__name__)

CKAN_SQL_URL = "https://data.boston.gov/api/3/action/datastore_search_sql"
TOPIC = "complaints.raw"
PAGE_SIZE = 1000
RUN_AT = time(6, 0)
# With no cursor yet, start from the last day; history comes from replay, not sync.
FIRST_SYNC_LOOKBACK = timedelta(days=1)


@dataclass(frozen=True)
class Resource:
    id: str
    opened_at: Callable[[dict[str, str]], datetime]
    mapper: Callable[[dict[str, str], Protect], Complaint]
    # SQL condition and ordering on the open time, and how the cursor is written for them.
    time_expr: str
    cursor_literal: Callable[[datetime], str]


RESOURCES = (
    Resource(
        id="1a0b420d-99f1-4887-9851-990b2a5a6e17",
        opened_at=legacy_opened_at,
        mapper=map_legacy,
        # A timestamp column in Boston local time with no offset.
        time_expr='"open_dt"',
        cursor_literal=lambda c: c.astimezone(BOSTON_TZ).replace(tzinfo=None).isoformat(),
    ),
    Resource(
        id="254adca6-64ab-4c5c-9fc0-a6da622be185",
        opened_at=new_opened_at,
        mapper=map_new,
        # Stored as text with a UTC offset, so it must be cast to compare as time.
        time_expr='"open_date"::timestamptz',
        cursor_literal=lambda c: c.astimezone(UTC).isoformat(),
    ),
)

FetchPage = Callable[[Resource, datetime, int], Awaitable[list[dict[str, str]]]]


def ckan_fetcher(client: httpx.AsyncClient) -> FetchPage:
    async def fetch(resource: Resource, cursor: datetime, limit: int) -> list[dict[str, str]]:
        # `>=` re-reads rows sharing the cursor's timestamp; consumers upsert, so that is safe
        # and no row tied with a page boundary is skipped.
        sql = (
            f'SELECT * FROM "{resource.id}" '
            f"WHERE {resource.time_expr} >= '{resource.cursor_literal(cursor)}' "
            f"ORDER BY {resource.time_expr} LIMIT {limit}"
        )
        response = await client.get(CKAN_SQL_URL, params={"sql": sql})
        response.raise_for_status()
        return [_as_text(r) for r in response.json()["result"]["records"]]

    return fetch


def _as_text(record: dict[str, Any]) -> dict[str, str]:
    # The API returns numbers and nulls where the CSVs have strings; mappers expect the CSV shape.
    return {k: "" if v is None else str(v) for k, v in record.items()}


async def sync_resource(
    resource: Resource,
    fetch: FetchPage,
    producer: AIOKafkaProducer,
    protect: Protect,
    now: datetime,
    page_size: int = PAGE_SIZE,
) -> None:
    async with Session() as session:
        state = await session.get(SyncStateRow, resource.id)
    cursor = state.last_opened_at if state else now - FIRST_SYNC_LOOKBACK
    published = 0
    while True:
        rows = await fetch(resource, cursor, page_size)
        for row in rows:
            complaint = resource.mapper(row, protect)
            await publish(producer, TOPIC, complaint.key, complaint)
        published += len(rows)
        if not rows:
            break
        newest = max(resource.opened_at(r) for r in rows)
        # The cursor only moves after the page is acknowledged by Kafka.
        await _save_cursor(resource.id, newest)
        if len(rows) < page_size or newest == cursor:
            break
        cursor = newest
    log.info("synced %d rows", published, extra={"resource_id": resource.id})


async def _save_cursor(resource_id: str, opened_at: datetime) -> None:
    stmt = insert(SyncStateRow).values(resource_id=resource_id, last_opened_at=opened_at)
    async with Session.begin() as session:
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["resource_id"], set_={"last_opened_at": opened_at}
            )
        )


def seconds_until_next_run(now: datetime) -> float:
    local = now.astimezone(BOSTON_TZ)
    run = datetime.combine(local.date(), RUN_AT, tzinfo=BOSTON_TZ)
    if run <= local:
        run = datetime.combine(local.date() + timedelta(days=1), RUN_AT, tzinfo=BOSTON_TZ)
    return (run - local).total_seconds()


async def sync_all(producer: AIOKafkaProducer, protect: Protect) -> None:
    async with httpx.AsyncClient(timeout=60) as client:
        fetch = ckan_fetcher(client)
        for resource in RESOURCES:
            await sync_resource(resource, fetch, producer, protect, datetime.now(UTC))


async def run(once: bool) -> None:
    protect = make_protect()
    producer = make_producer()
    await producer.start()
    try:
        while True:
            if not once:
                await asyncio.sleep(seconds_until_next_run(datetime.now(UTC)))
            try:
                await sync_all(producer, protect)
            except Exception:
                # The cursor only advanced for pages that were published, so the next run
                # picks up where this one stopped.
                log.exception("sync failed")
                if once:
                    raise
            if once:
                return
    finally:
        await producer.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync new 311 records from data.boston.gov.")
    parser.add_argument("--once", action="store_true", help="sync now instead of daily at 06:00 ET")
    args = parser.parse_args()
    setup_logging()
    asyncio.run(run(args.once))


if __name__ == "__main__":
    main()
