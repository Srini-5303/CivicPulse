import argparse
import asyncio
import csv
import logging
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

from cryptography.fernet import Fernet

from libs.common.config import settings
from libs.common.kafka import make_producer, publish
from libs.common.logging import setup_logging
from libs.common.schemas import Complaint
from services.ingestion.mappers import map_legacy

log = logging.getLogger(__name__)

DATA_DIR = Path("data/311")
TOPIC = "complaints.raw"


def pacing_delay(previous: datetime, current: datetime, speed: float) -> float:
    return (current - previous).total_seconds() / speed


def load_legacy(start: date, end: date) -> Iterator[Complaint]:
    fernet = Fernet(settings.pii_key)

    def encrypt(text: str) -> str:
        return fernet.encrypt(text.encode()).decode()

    first, last = start.isoformat(), end.isoformat()
    for path in sorted(DATA_DIR.glob("legacy_*.csv")):
        with path.open(newline="") as f:
            for row in csv.DictReader(f):
                # Cheap string filter on the ISO date prefix before parsing the whole row.
                if first <= row["open_dt"][:10] <= last:
                    yield map_legacy(row, encrypt)


async def replay(start: date, end: date, speed: float) -> None:
    complaints = sorted(load_legacy(start, end), key=lambda c: c.opened_at)
    log.info("replaying %d complaints", len(complaints))
    producer = make_producer()
    await producer.start()
    try:
        previous = None
        for complaint in complaints:
            if previous is not None:
                await asyncio.sleep(pacing_delay(previous, complaint.opened_at, speed))
            await publish(producer, TOPIC, complaint.key, complaint)
            previous = complaint.opened_at
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
