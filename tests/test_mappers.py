from services.ingestion.mappers import map_legacy

ROW = {
    "case_enquiry_id": "101005839033",
    "open_dt": "2025-01-02 09:50:33.593",
    "type": "Requests for Street Cleaning",
    "case_title": "Requests for Street Cleaning",
}


def test_city_hall_placeholder_means_no_location() -> None:
    placeholder = map_legacy({**ROW, "latitude": "42.3594", "longitude": "-71.0587"}, str)
    real = map_legacy({**ROW, "latitude": "42.34265", "longitude": "-71.09711"}, str)

    assert (placeholder.lat, placeholder.lon) == (None, None)
    assert (real.lat, real.lon) == (42.34265, -71.09711)
