import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from pydantic import BaseModel

from libs.common.config import settings
from libs.common.schemas import DeadLetter

log = logging.getLogger(__name__)

RETRY_DELAYS = (1.0, 4.0, 16.0)


def make_producer() -> AIOKafkaProducer:
    return AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap, acks="all")


def make_consumer(topic: str, group: str) -> AIOKafkaConsumer:
    # Manual commits: an offset only moves after the handler's DB write succeeded.
    return AIOKafkaConsumer(
        topic,
        bootstrap_servers=settings.kafka_bootstrap,
        group_id=group,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )


async def publish(producer: AIOKafkaProducer, topic: str, key: str, message: BaseModel) -> None:
    await producer.send_and_wait(topic, message.model_dump_json().encode(), key=key.encode())


async def run_consumer[M: BaseModel](
    consumer: Any,
    producer: Any,
    model: type[M],
    handler: Callable[[M], Awaitable[None]],
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    async for record in consumer:
        await _process(record, producer, model, handler, sleep)
        await consumer.commit({TopicPartition(record.topic, record.partition): record.offset + 1})


async def _process[M: BaseModel](
    record: Any,
    producer: Any,
    model: type[M],
    handler: Callable[[M], Awaitable[None]],
    sleep: Callable[[float], Awaitable[None]],
) -> None:
    ctx = {"topic": record.topic, "offset": record.offset}
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            await handler(model.model_validate_json(record.value))
            return
        except Exception as exc:
            error = exc
            if attempt < len(RETRY_DELAYS):
                log.warning("handler failed, retrying", extra=ctx, exc_info=True)
                await sleep(RETRY_DELAYS[attempt])

    log.error("handler failed, sending to DLQ", extra=ctx, exc_info=error)
    dead = DeadLetter(
        topic=record.topic,
        partition=record.partition,
        offset=record.offset,
        error_type=type(error).__name__,
        payload=record.value.decode(),
    )
    await producer.send_and_wait(
        f"{record.topic}.dlq", dead.model_dump_json().encode(), key=record.key
    )
