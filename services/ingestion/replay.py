import argparse
import asyncio
import csv
import logging
from collections.abc import Callable, Iterator
from datetime import date, datetime
from pathlib import Path

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

DATA_DIR = Path("data/311")
TOPIC = "complaints.raw"


def pacing_delay(previous: datetime, current: datetime, speed: float) -> float:
    return (current - previous).total_seconds() / speed


Mapper = Callable[[dict[str, str], Protect], Complaint]
SOURCES: tuple[tuple[str, Callable[[dict[str, str]], datetime], Mapper], ...] = (
    ("legacy_*.csv", legacy_opened_at, map_legacy),
    ("new_*.csv", new_opened_at, map_new),
)


def load(start: date, end: date) -> Iterator[tuple[datetime, Mapper, dict[str, str]]]:
    """Rows opened on [start, end] Boston local dates, unmapped so scrubbing waits for publish."""
    for pattern, opened_at, mapper in SOURCES:
        for path in sorted(DATA_DIR.glob(pattern)):
            with path.open(newline="") as f:
                for row in csv.DictReader(f):
                    opened = opened_at(row)
                    if start <= opened.astimezone(BOSTON_TZ).date() <= end:
                        yield opened, mapper, row


async def replay(start: date, end: date, speed: float) -> None:
    rows = sorted(load(start, end), key=lambda r: r[0])
    log.info("replaying %d complaints", len(rows))
    protect = make_protect()
    producer = make_producer()
    await producer.start()
    try:
        previous = None
        for opened, mapper, row in rows:
            if previous is not None:
                await asyncio.sleep(pacing_delay(previous, opened, speed))
            complaint = mapper(row, protect)
            await publish(producer, TOPIC, complaint.key, complaint)
            previous = opened
    finally:
        await producer.stop()
    log.info("replay done")


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay historical 311 records into Kafka.")
    parser.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
    parser.add_argument("--to", dest="end", type=date.fromisoformat, required=True)
    parser.add_argument("--speed", type=float, default=1.0, help="1 is real time")
    args = parser.parse_args()
    setup_logging()
    asyncio.run(replay(args.start, args.end, args.speed))


if __name__ == "__main__":
    main()
