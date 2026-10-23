import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta

from aiokafka import AIOKafkaProducer
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from libs.common.db import ComplaintRow, IncidentComplaintRow, IncidentRow, Session
from libs.common.kafka import make_producer, publish, serve
from libs.common.logging import setup_logging
from libs.common.schemas import Incident, TriagedComplaint
from services.hotspot.clustering import centroid, find_clusters, match_incident

log = logging.getLogger(__name__)

WINDOW = timedelta(hours=2)
STEP = timedelta(seconds=60)
# A full day of event-time quiet: shorter splits issues reported in the evening and again the
# next morning (half of nearby same-type repeats in 2025 came 6+ h apart).
CLOSE_AFTER = timedelta(hours=24)
TOPIC = "incidents.detected"


class Detector:
    """Runs detection whenever event time (complaint `opened_at`) advances by a step."""

    def __init__(self, producer: AIOKafkaProducer) -> None:
        self.producer = producer
        self.next_run: datetime | None = None

    async def handle(self, complaint: TriagedComplaint) -> None:
        if self.next_run is not None:
            # A jump back past the whole window means a replay of older data started after
            # newer data; treat it as a new timeline instead of skipping all of it.
            rewound = complaint.opened_at < self.next_run - STEP - WINDOW
            if complaint.opened_at < self.next_run and not rewound:
                return
        await detect(self.producer, complaint.opened_at)
        # A jump of several steps (e.g. a daily sync batch) runs once, not once per step.
        self.next_run = complaint.opened_at + STEP


async def detect(producer: AIOKafkaProducer, now: datetime) -> None:
    async with Session.begin() as session:
        await close_quiet_incidents(session, now)
        rows = await session.execute(
            select(ComplaintRow.id, ComplaintRow.category, ComplaintRow.lat, ComplaintRow.lon)
            .where(ComplaintRow.opened_at > now - WINDOW, ComplaintRow.opened_at <= now)
            .where(ComplaintRow.lat.is_not(None), ComplaintRow.category.is_not(None))
            .order_by(ComplaintRow.id)
        )
        by_category: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
        for cid, category, lat, lon in rows:
            by_category[category].append((cid, lat, lon))

        new_incidents = []
        for category, complaints in by_category.items():
            clusters = find_clusters([(lat, lon) for _, lat, lon in complaints])
            if not clusters:
                continue
            open_rows = await session.execute(
                select(IncidentRow.id, IncidentRow.centroid_lat, IncidentRow.centroid_lon).where(
                    IncidentRow.category == category, IncidentRow.status == "open"
                )
            )
            open_incidents = {iid: (lat, lon) for iid, lat, lon in open_rows}
            for cluster in clusters:
                members = [complaints[i] for i in cluster]
                center = centroid([(lat, lon) for _, lat, lon in members])
                complaint_ids = [cid for cid, _, _ in members]
                incident_id = match_incident(center, open_incidents)
                if incident_id is None:
                    # Deterministic so a retried run republishes the same incident, not a twin.
                    incident_id = uuid.uuid5(
                        uuid.NAMESPACE_URL, f"civicpulse:incident:{category}:{complaint_ids[0]}"
                    )
                    await session.execute(
                        insert(IncidentRow)
                        .values(
                            id=incident_id,
                            category=category,
                            centroid_lat=center[0],
                            centroid_lon=center[1],
                            status="open",
                            detected_at=now,
                        )
                        .on_conflict_do_nothing()
                    )
                    open_incidents[incident_id] = center
                    new_incidents.append(
                        Incident(
                            incident_id=incident_id,
                            category=category,
                            centroid_lat=center[0],
                            centroid_lon=center[1],
                            detected_at=now,
                            complaint_ids=complaint_ids,
                        )
                    )
                await session.execute(
                    insert(IncidentComplaintRow)
                    .values(
                        [{"incident_id": incident_id, "complaint_id": c} for c in complaint_ids]
                    )
                    .on_conflict_do_nothing()
                )

        # Only new incidents start a workflow; attaching complaints just updates the links.
        # Publishing before commit means a failed commit is retried and republishes the same IDs.
        for incident in new_incidents:
            log.info("incident detected", extra={"incident_id": str(incident.incident_id)})
            await publish(producer, TOPIC, str(incident.incident_id), incident)


async def close_quiet_incidents(session: AsyncSession, now: datetime) -> None:
    quiet = (
        select(IncidentComplaintRow.incident_id)
        .join(ComplaintRow, ComplaintRow.id == IncidentComplaintRow.complaint_id)
        .group_by(IncidentComplaintRow.incident_id)
        .having(func.max(ComplaintRow.opened_at) < now - CLOSE_AFTER)
    )
    await session.execute(
        update(IncidentRow)
        .where(IncidentRow.status == "open", IncidentRow.id.in_(quiet))
        .values(status="closed")
    )


async def main() -> None:
    setup_logging()
    producer = make_producer()
    await producer.start()
    try:
        detector = Detector(producer)
        await serve("complaints.triaged", "hotspot", producer, TriagedComplaint, detector.handle)
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
