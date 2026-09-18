"""Unit tests for PaddleOCR document ingestion parser (REC-61)."""

from pathlib import Path

import pytest

from contracts.document import BlockType, IngestRequest
from services.ingestion.parsers.paddle_ocr import PaddleOCRParser
from services.ingestion.service import IngestionService


@pytest.fixture
def sample_pdf_path() -> str:
    """Returns path to a small fixture PDF."""
    path = Path("data/documents/system_architecture_spec.pdf")
    if not path.exists():
        pytest.skip("Test fixture PDF not found")
    return str(path)


def test_paddle_ocr_parser_init() -> None:
    """Verifies default parameters and lazy initialization of PaddleOCRParser."""
    parser = PaddleOCRParser(lang="en", use_angle_cls=True, dpi=150, confidence_threshold=0.40)
    assert parser.lang == "en"
    assert parser.use_angle_cls is True
    assert parser.dpi == 150
    assert parser.confidence_threshold == 0.40
    assert parser._initialized is False


def test_paddle_ocr_parser_parse_fallback(sample_pdf_path: str) -> None:
    """Verifies that PaddleOCRParser executes successfully even with fallback on real documents."""
    parser = PaddleOCRParser()
    blocks = parser.parse(sample_pdf_path, doc_id="test_paddle_doc")

    assert len(blocks) > 0
    first_block = blocks[0]
    assert first_block.doc_id == "test_paddle_doc"
    assert first_block.page >= 1
    assert len(first_block.bbox) == 4
    assert isinstance(first_block.text, str)
    assert len(first_block.text) > 0
    assert first_block.type in (BlockType.TEXT, BlockType.HEADING, BlockType.TABLE, BlockType.IMAGE)


def test_ingestion_service_paddleocr_route(sample_pdf_path: str) -> None:
    """Verifies that IngestionService correctly dispatches profile_override='paddleocr'."""
    service = IngestionService()
    assert hasattr(service, "paddle_parser")

    req = IngestRequest(file_path=sample_pdf_path, profile_override="paddleocr")
    res = service.parse(req)

    assert res.doc_id is not None
    assert len(res.blocks) > 0
    # Every block has required bbox and page
    for b in res.blocks:
        assert b.page >= 1
        assert len(b.bbox) == 4
        assert b.bbox[2] >= b.bbox[0]
        assert b.bbox[3] >= b.bbox[1]
