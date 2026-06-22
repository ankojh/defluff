from types import SimpleNamespace

import httpx

from app.content import _extract_pdf, _is_probably_pdf_url
from app.models import ContentKind


def test_pdf_url_detection_handles_query_strings() -> None:
    assert _is_probably_pdf_url("https://example.com/report.pdf?download=1")


def test_extract_pdf_returns_page_text(monkeypatch) -> None:
    url = "https://example.com/report.pdf"

    def fake_get(*args, **kwargs) -> httpx.Response:
        request = httpx.Request("GET", url)
        return httpx.Response(
            200,
            content=b"%PDF fake",
            headers={"content-type": "application/pdf"},
            request=request,
        )

    class FakePage:
        def extract_text(self) -> str:
            return " Important PDF text. \n\n More detail. "

    class FakePdfReader:
        metadata = SimpleNamespace(title="Report Title")
        pages = [FakePage()]

        def __init__(self, *args, **kwargs) -> None:
            pass

    monkeypatch.setattr("app.content.httpx.get", fake_get)
    monkeypatch.setattr("app.content.PdfReader", FakePdfReader)

    response = _extract_pdf(url)

    assert response.kind == ContentKind.pdf
    assert response.title == "Report Title"
    assert response.source == "pdf"
    assert response.text == "Important PDF text.\nMore detail."
    assert response.blocks[0].text == "Page 1\nImportant PDF text.\nMore detail."
