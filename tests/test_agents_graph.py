import uuid
from datetime import UTC, datetime

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

from libs.common.config import settings
from libs.common.db import IncidentRow, Session, psycopg_url
from libs.common.schemas import ApprovedResponse, Incident
from services.agents.graph import IncidentState, build_graph
from tests.fakes import FakeProducer


async def test_review_survives_restart_and_publishes_on_approve() -> None:
    now = datetime.now(UTC)
    incident = Incident(
        incident_id=uuid.uuid4(),
        category="Pothole",
        centroid_lat=42.35,
        centroid_lon=-71.06,
        detected_at=now,
        complaint_ids=["legacy:1", "legacy:2"],
    )
    async with Session.begin() as session:
        session.add(
            IncidentRow(
                id=incident.incident_id,
                category="Pothole",
                centroid_lat=42.35,
                centroid_lon=-71.06,
                detected_at=now,
            )
        )
    draft_id = uuid.uuid4()
    config = {"configurable": {"thread_id": str(draft_id)}}
    url = psycopg_url(settings.database_url)
    producer = FakeProducer()

    async with AsyncPostgresSaver.from_conn_string(url) as saver:
        graph = build_graph(saver, producer)
        await graph.ainvoke(IncidentState(incident=incident, draft_id=draft_id), config)
        assert (await graph.aget_state(config)).next == ("human_review",)

    # A fresh checkpointer connection stands in for a restarted agents service.
    async with AsyncPostgresSaver.from_conn_string(url) as saver:
        graph = build_graph(saver, producer)
        await graph.ainvoke(Command(resume={"decision": "approve"}), config)

    [(topic, value)] = producer.sent
    assert topic == "responses.approved"
    assert ApprovedResponse.model_validate_json(value).draft_id == draft_id
