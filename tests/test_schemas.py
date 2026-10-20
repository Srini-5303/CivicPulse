import pytest
from pydantic import ValidationError

from libs.common.schemas import ReviewDecision


def test_rejection_requires_reason() -> None:
    with pytest.raises(ValidationError):
        ReviewDecision(decision="reject")
