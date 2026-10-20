import asyncio
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

from libs.common.config import settings
from libs.common.db import psycopg_url
from libs.common.kafka import make_producer, serve
from libs.common.logging import setup_logging
from libs.common.schemas import Incident, ReviewDecision
from services.agents.graph import IncidentState, build_graph

graph = None


def thread_config(draft_id: uuid.UUID | str) -> dict:
    return {"configurable": {"thread_id": str(draft_id)}}


async def handle_incident(incident: Incident) -> None:
    # One draft per incident: a redelivered message finds the existing thread and stops.
    draft_id = uuid.uuid5(uuid.NAMESPACE_URL, f"civicpulse:draft:{incident.incident_id}")
    config = thread_config(draft_id)
    if (await graph.aget_state(config)).values:
        return
    await graph.ainvoke(IncidentState(incident=incident, draft_id=draft_id), config)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global graph
    setup_logging()
    producer = make_producer()
    await producer.start()
    async with AsyncPostgresSaver.from_conn_string(psycopg_url(settings.database_url)) as saver:
        graph = build_graph(saver, producer)
        consumer = asyncio.create_task(
            serve("incidents.detected", "agents", producer, Incident, handle_incident)
        )
        yield
        consumer.cancel()
    await producer.stop()


app = FastAPI(lifespan=lifespan)


@app.post("/threads/{thread_id}/resume")
async def resume(thread_id: uuid.UUID, decision: ReviewDecision) -> dict:
    config = thread_config(thread_id)
    if (await graph.aget_state(config)).next != ("human_review",):
        raise HTTPException(409, "thread is not waiting for review")
    await graph.ainvoke(Command(resume=decision.model_dump()), config)
    return {"status": "resumed"}
