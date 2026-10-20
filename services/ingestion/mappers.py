from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from libs.common.schemas import Complaint

BOSTON_TZ = ZoneInfo("America/New_York")

# Legacy rows with no real location carry City Hall's coordinates instead of blanks.
CITY_HALL_PLACEHOLDER = (42.3594, -71.0587)


def map_legacy(row: dict[str, str], encrypt: Callable[[str], str]) -> Complaint:
    lat, lon = _legacy_location(row["latitude"], row["longitude"])
    return Complaint(
        source="legacy",
        source_id=row["case_enquiry_id"],
        opened_at=datetime.fromisoformat(row["open_dt"]).replace(tzinfo=BOSTON_TZ),
        lat=lat,
        lon=lon,
        category_raw=row["type"],
        # Legacy records have no description field; the case title is the resident's text.
        raw_text_enc=encrypt(row["case_title"]),
        # Empty until the Presidio scrub lands, so unscrubbed text can never reach an LLM.
        text_scrubbed="",
    )


def _legacy_location(lat: str, lon: str) -> tuple[float | None, float | None]:
    if not lat or not lon:
        return None, None
    point = (float(lat), float(lon))
    if point == CITY_HALL_PLACEHOLDER:
        return None, None
    return point
