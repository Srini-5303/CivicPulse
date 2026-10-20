from datetime import datetime, timedelta

from services.ingestion.replay import pacing_delay


def test_speed_144_replays_a_day_in_ten_minutes() -> None:
    start = datetime(2025, 1, 1)
    assert pacing_delay(start, start + timedelta(days=1), speed=144) == 600
