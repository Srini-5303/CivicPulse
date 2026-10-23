import csv
import logging
from collections.abc import Callable
from datetime import datetime
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

from libs.common.schemas import Complaint

log = logging.getLogger(__name__)

BOSTON_TZ = ZoneInfo("America/New_York")
CATEGORIES_CSV = Path("data/categories.csv")

# Rows with no real location carry City Hall's coordinates or address instead of blanks.
CITY_HALL_PLACEHOLDER = (42.3594, -71.0587)
CITY_HALL_PLACEHOLDER_STREETS = {"1 City Hall Plz", "100 City Hall Plz"}

# Takes the resident's text, returns (Fernet-encrypted text, scrubbed text).
Protect = Callable[[str], tuple[str, str]]


@cache
def _legacy_categories() -> dict[str, tuple[str, str]]:
    with CATEGORIES_CSV.open(newline="") as f:
        return {r["legacy_type"]: (r["category"], r["department"]) for r in csv.DictReader(f)}


def legacy_opened_at(row: dict[str, str]) -> datetime:
    # Legacy timestamps are Boston local time without an offset.
    return datetime.fromisoformat(row["open_dt"]).replace(tzinfo=BOSTON_TZ)


def new_opened_at(row: dict[str, str]) -> datetime:
    # New-system timestamps carry a UTC offset ("...+00").
    return datetime.fromisoformat(row["open_date"])


def map_legacy(row: dict[str, str], protect: Protect) -> Complaint:
    category, department = _legacy_categories().get(row["type"], (None, None))
    if category is None:
        log.warning("legacy type missing from categories.csv", extra={"category": row["type"]})
        category, department = row["type"], row["department"]
    lat, lon = _location(row["latitude"], row["longitude"], row["location_street_name"])
    # Legacy records have no description field; the case title is the closest thing to it.
    raw_text_enc, text_scrubbed = protect(row["case_title"])
    return Complaint(
        source="legacy",
        source_id=row["case_enquiry_id"],
        opened_at=legacy_opened_at(row),
        lat=lat,
        lon=lon,
        category_raw=row["type"],
        source_category=category,
        source_department=department,
        raw_text_enc=raw_text_enc,
        text_scrubbed=text_scrubbed,
    )


def map_new(row: dict[str, str], protect: Protect) -> Complaint:
    # A few rows leave service_name blank but keep the same value in case_topic.
    service = row["service_name"] or row["case_topic"] or "Other"
    street = f"{row['street_number']} {row['street_name']}".strip()
    lat, lon = _location(row["latitude"], row["longitude"], street)
    # The new system has no description field either; the service name stands in for it.
    raw_text_enc, text_scrubbed = protect(service)
    return Complaint(
        source="new",
        source_id=row["case_id"],
        opened_at=new_opened_at(row),
        lat=lat,
        lon=lon,
        category_raw=service,
        source_category=service,
        source_department=row["assigned_department"] or None,
        raw_text_enc=raw_text_enc,
        text_scrubbed=text_scrubbed,
    )


def _location(lat: str, lon: str, street: str) -> tuple[float | None, float | None]:
    if not lat or not lon or street in CITY_HALL_PLACEHOLDER_STREETS:
        return None, None
    point = (float(lat), float(lon))
    if point == CITY_HALL_PLACEHOLDER:
        return None, None
    return point
