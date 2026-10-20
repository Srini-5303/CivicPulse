import asyncio
import uuid

from sqlalchemy.dialects.postgresql import insert

from libs.common.db import AuditLogRow, OutboxRow, Session
from libs.common.kafka import make_producer, serve
from libs.common.logging import setup_logging
from libs.common.schemas import ApprovedResponse

# Who receives a public response is still undecided; dev writes everything to the outbox.
DEV_RECIPIENT = "outbox@localhost"


async def handle(response: ApprovedResponse) -> None:
    # Deterministic ID so a redelivered message neither sends twice nor double-audits.
    outbox_id = uuid.uuid5(uuid.NAMESPACE_URL, f"civicpulse:outbox:{response.draft_id}")
    async with Session.begin() as session:
        result = await session.execute(
            insert(OutboxRow)
            .values(
                id=outbox_id,
                draft_id=response.draft_id,
                recipient=DEV_RECIPIENT,
                subject="Update on your 311 report",
                body=response.text,
            )
            .on_conflict_do_nothing()
        )
        if result.rowcount:
            session.add(
                AuditLogRow(actor="notifier", action="response.sent", draft_id=response.draft_id)
            )


async def main() -> None:
    setup_logging()
    producer = make_producer()
    await producer.start()
    try:
        await serve("responses.approved", "notifier", producer, ApprovedResponse, handle)
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
