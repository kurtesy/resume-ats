import pytest
from app.core import parse_document

@pytest.mark.anyio
async def test_parse_document_txt() -> None:
    content = b"Hello, Resume Matcher text parser!"
    result = await parse_document(content, "resume.txt")
    assert result == "Hello, Resume Matcher text parser!"

@pytest.mark.anyio
async def test_parse_document_md() -> None:
    content = b"# Resume Matcher\nMarkdown file"
    result = await parse_document(content, "resume.md")
    assert result == "# Resume Matcher\nMarkdown file"

@pytest.mark.anyio
async def test_parse_document_unsupported() -> None:
    content = b"random data"
    with pytest.raises(ValueError, match="Unsupported document format"):
        await parse_document(content, "resume.xlsx")