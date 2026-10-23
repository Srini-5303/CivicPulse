import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from libs.common.config import settings
from libs.common.kafka import make_producer, publish
from libs.common.logging import setup_logging
from libs.common.schemas import Complaint
from services.ingestion.privacy import make_protect

log = logging.getLogger(__name__)

TOPIC = "complaints.raw"
RATE_LIMIT_PER_MINUTE = 10


class ResidentComplaint(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    # Required because there is no geocoder; the bounds cover Boston, so a swapped or
    # mistyped coordinate is rejected instead of skewing hotspots.
    lat: float = Field(ge=42.22, le=42.41)
    lon: float = Field(ge=-71.20, le=-70.95)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    app.state.protect = make_protect()
    app.state.redis = Redis.from_url(settings.redis_url)
    app.state.producer = make_producer()
    await app.state.producer.start()
    yield
    await app.state.producer.stop()
    await app.state.redis.aclose()


app = FastAPI(lifespan=lifespan)


async def allow(redis: Redis, ip: str) -> bool:
    # Fixed one-minute window: simple, and a burst of up to 2x at a window edge is harmless here.
    key = f"ratelimit:complaints:{ip}:{int(time.time() // 60)}"
    count, _ = await redis.pipeline().incr(key).expire(key, 60).execute()
    return count <= RATE_LIMIT_PER_MINUTE


@app.post("/complaints", status_code=202)
async def submit(body: ResidentComplaint, request: Request) -> dict:
    state = request.app.state
    if not await allow(state.redis, request.client.host):
        raise HTTPException(429, "too many complaints from this address; try again in a minute")
    raw_text_enc, text_scrubbed = state.protect(body.text)
    complaint = Complaint(
        source="resident",
        source_id=uuid.uuid4().hex,
        opened_at=datetime.now(UTC),
        lat=body.lat,
        lon=body.lon,
        category_raw=None,
        source_category=None,
        source_department=None,
        raw_text_enc=raw_text_enc,
        text_scrubbed=text_scrubbed,
    )
    await publish(state.producer, TOPIC, complaint.key, complaint)
    log.info("resident complaint accepted", extra={"complaint_id": complaint.key})
    return {"reference_id": complaint.key}
