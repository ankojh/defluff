import pytest
from pydantic import ValidationError

from app.schemas import UrlSubmission


def test_url_submission_accepts_http_urls() -> None:
    submission = UrlSubmission(url="https://example.com/watch?v=123")

    assert str(submission.url) == "https://example.com/watch?v=123"


def test_url_submission_rejects_non_urls() -> None:
    with pytest.raises(ValidationError):
        UrlSubmission(url="not-a-url")
