from datetime import UTC, datetime

from services.ingestion.mappers import map_legacy, map_new


def protect(text: str) -> tuple[str, str]:
    return f"enc:{text}", f"scrubbed:{text}"


LEGACY = {
    "case_enquiry_id": "101005839033",
    "open_dt": "2025-01-02 09:50:33.593",
    "type": "Request for Pothole Repair",
    "department": "PWDx",
    "case_title": "Pothole",
    "location_street_name": "115 Jersey St",
    "latitude": "42.34265",
    "longitude": "-71.09711",
}

NEW = {
    "case_id": "BCS-00241302",
    "open_date": "2026-07-02 06:31:56.081933+00",
    "case_topic": "Trash Placed Out Early",
    "service_name": "Trash Placed Out Early",
    "assigned_department": "Public Works Department (PWD)",
    "street_number": "53",
    "street_name": "Union Park",
    "latitude": "42.34351289",
    "longitude": "-71.07206186",
}


def test_legacy_type_maps_to_canonical_category_in_boston_time() -> None:
    complaint = map_legacy(LEGACY, protect)

    assert complaint.source_category == "Pothole"
    assert complaint.source_department == "Public Works Department (PWD)"
    assert complaint.category_raw == "Request for Pothole Repair"
    assert complaint.opened_at == datetime(2025, 1, 2, 14, 50, 33, 593000, tzinfo=UTC)
    assert (complaint.raw_text_enc, complaint.text_scrubbed) == ("enc:Pothole", "scrubbed:Pothole")


def test_new_system_row_maps_in_utc_and_falls_back_to_case_topic() -> None:
    complaint = map_new({**NEW, "service_name": "", "case_topic": "Pothole"}, protect)

    assert complaint.key == "new:BCS-00241302"
    assert complaint.source_category == "Pothole"
    assert complaint.opened_at == datetime(2026, 7, 2, 6, 31, 56, 81933, tzinfo=UTC)
    assert (complaint.lat, complaint.lon) == (42.34351289, -71.07206186)


def test_city_hall_placeholder_means_no_location_in_both_systems() -> None:
    placeholders = [
        map_legacy({**LEGACY, "latitude": "42.3594", "longitude": "-71.0587"}, protect),
        map_legacy({**LEGACY, "location_street_name": "100 City Hall Plz"}, protect),
        map_new({**NEW, "street_number": "1", "street_name": "City Hall Plz"}, protect),
    ]

    assert all((c.lat, c.lon) == (None, None) for c in placeholders)
