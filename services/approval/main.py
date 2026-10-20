from html import escape
from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select

from libs.common.config import settings
from libs.common.db import ApprovalRow, AuditLogRow, DraftRow, Session
from libs.common.logging import setup_logging
from libs.common.schemas import ReviewDecision

# Placeholder reviewer until JWT auth lands.
REVIEWER = "dev"

setup_logging()
app = FastAPI()


@app.get("/", response_class=HTMLResponse)
async def queue() -> str:
    async with Session() as session:
        drafts = await session.scalars(
            select(DraftRow).where(DraftRow.status == "pending").order_by(DraftRow.created_at)
        )
        items = "".join(_draft_html(d) for d in drafts)
    body = items or "<p>None.</p>"
    return f"<!doctype html><title>Review queue</title><h1>Pending drafts</h1>{body}"


def _draft_html(draft: DraftRow) -> str:
    return f"""
    <section>
      <p>{escape(draft.draft_text)}</p>
      <form method="post" action="/drafts/{draft.id}/decision">
        <input name="reason" placeholder="Reason (required to reject)">
        <button name="decision" value="approve">Approve</button>
        <button name="decision" value="reject">Reject</button>
      </form>
    </section>"""


@app.post("/drafts/{draft_id}/decision")
async def decide(
    draft_id: UUID,
    decision: Annotated[Literal["approve", "reject"], Form()],
    reason: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    try:
        review = ReviewDecision(decision=decision, reason=reason or None)
    except ValidationError:
        raise HTTPException(400, "a rejection needs a reason") from None
    # Records and resume share one transaction: a failed resume leaves no decision on file.
    async with Session.begin() as session:
        session.add(
            ApprovalRow(
                draft_id=draft_id, reviewer=REVIEWER, decision=decision, reason=review.reason
            )
        )
        session.add(
            AuditLogRow(
                actor=REVIEWER,
                action=f"draft.{decision}",
                draft_id=draft_id,
                details={"reason": review.reason},
            )
        )
        await session.flush()
        async with httpx.AsyncClient(base_url=settings.agents_url) as client:
            response = await client.post(f"/threads/{draft_id}/resume", json=review.model_dump())
            response.raise_for_status()
    return RedirectResponse("/", status_code=303)
