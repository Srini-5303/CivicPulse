import uuid

from sqlalchemy import func, select

from libs.common.db import AuditLogRow, DraftRow, OutboxRow, Session
from libs.common.schemas import ApprovedResponse
from services.notifier.main import handle


async def test_redelivered_response_is_sent_and_audited_once() -> None:
    draft_id = uuid.uuid4()
    async with Session.begin() as session:
        session.add(DraftRow(id=draft_id, draft_text="text", status="published"))
    response = ApprovedResponse(
        draft_id=draft_id, incident_id=None, complaint_ids=[], text="text", risk_tier="review"
    )

    await handle(response)
    await handle(response)

    async with Session() as session:
        for table in (OutboxRow, AuditLogRow):
            count = await session.scalar(
                select(func.count()).select_from(table).where(table.draft_id == draft_id)
            )
            assert count == 1
