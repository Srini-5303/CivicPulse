from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, model_validator


class Complaint(BaseModel):
    schema_version: int = 1
    source: Literal["legacy", "new", "resident"]
    source_id: str
    opened_at: datetime
    # None when the source has no real location (e.g. the legacy City Hall placeholder).
    lat: float | None
    lon: float | None
    category_raw: str
    raw_text_enc: str
    text_scrubbed: str

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"


class TriagedComplaint(Complaint):
    category: str
    department: str
    urgency: Literal["low", "medium", "high"]
    duplicate_of: str | None
    triage_tier: int


class Incident(BaseModel):
    schema_version: int = 1
    incident_id: UUID
    category: str
    centroid_lat: float
    centroid_lon: float
    detected_at: datetime
    complaint_ids: list[str]


class ApprovedResponse(BaseModel):
    schema_version: int = 1
    draft_id: UUID
    incident_id: UUID | None
    complaint_ids: list[str]
    text: str
    risk_tier: Literal["auto", "review", "priority"]


class ReviewDecision(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str | None = None

    @model_validator(mode="after")
    def reject_needs_reason(self) -> "ReviewDecision":
        if self.decision == "reject" and not self.reason:
            raise ValueError("a rejection needs a reason")
        return self


class DeadLetter(BaseModel):
    schema_version: int = 1
    topic: str
    partition: int
    offset: int
    error_type: str
    payload: str
