from libs.common.pii import scrub


def test_scrub_removes_personal_data_and_generalizes_house_numbers() -> None:
    text = "John Smith, 617-555-0134, js@example.com, reports a pothole at 245 Elm St and 42 Oak St"

    assert scrub(text) == (
        "[REDACTED: PERSON], [REDACTED: PHONE_NUMBER], [REDACTED: EMAIL_ADDRESS], reports a "
        "pothole at the 200 block of Elm St and the unit block of Oak St"
    )


def test_scrub_keeps_category_titles_and_intersections() -> None:
    for text in ("Missed Trash: District 07", "Illegal Graffiti", "INTERSECTION of Kilmarnock St"):
        assert scrub(text) == text
