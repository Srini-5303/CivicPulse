from typing import Any
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert

from libs.common.db import DraftRow, Session
from libs.common.kafka import publish
from libs.common.schemas import ApprovedResponse, Incident, ReviewDecision


class IncidentState(BaseModel):
    incident: Incident
    draft_id: UUID
    draft_text: str = ""
    decision: ReviewDecision | None = None


def build_graph(checkpointer: BaseCheckpointSaver, producer: Any):
    async def draft(state: IncidentState) -> dict:
        # Placeholder until investigate, retrieve, and the LLM drafting nodes land.
        text = (
            f"We have received {len(state.incident.complaint_ids)} reports of "
            f"{state.incident.category} in one area and referred them to the responsible team."
        )
        async with Session.begin() as session:
            await session.execute(
                insert(DraftRow)
                .values(
                    id=state.draft_id,
                    incident_id=state.incident.incident_id,
                    draft_text=text,
                    risk_tier="review",
                    status="pending",
                )
                .on_conflict_do_nothing()
            )
        return {"draft_text": text}

    async def human_review(state: IncidentState) -> dict:
        # On resume this node reruns from the top and interrupt() returns the decision.
        decision = ReviewDecision.model_validate(interrupt({"draft_id": str(state.draft_id)}))
        if decision.decision == "reject":
            await _set_status(state.draft_id, "rejected")
        return {"decision": decision}

    async def publish_response(state: IncidentState) -> dict:
        response = ApprovedResponse(
            draft_id=state.draft_id,
            incident_id=state.incident.incident_id,
            complaint_ids=state.incident.complaint_ids,
            text=state.draft_text,
            risk_tier="review",
        )
        await publish(producer, "responses.approved", str(state.draft_id), response)
        await _set_status(state.draft_id, "published")
        return {}

    def route(state: IncidentState) -> str:
        assert state.decision is not None
        return "publish" if state.decision.decision == "approve" else END

    graph = StateGraph(IncidentState)
    graph.add_node("draft", draft)
    graph.add_node("human_review", human_review)
    graph.add_node("publish", publish_response)
    graph.add_edge(START, "draft")
    graph.add_edge("draft", "human_review")
    graph.add_conditional_edges("human_review", route, ["publish", END])
    graph.add_edge("publish", END)
    return graph.compile(checkpointer=checkpointer)


async def _set_status(draft_id: UUID, status: str) -> None:
    async with Session.begin() as session:
        await session.execute(update(DraftRow).where(DraftRow.id == draft_id).values(status=status))
