import logging
from pathlib import Path
import pdfplumber

logger = logging.getLogger(__name__)


def load_pdf_pages(pdf_path: str | Path) -> list[str]:
    """Return per-page text.
        Side-effecting (opens a file). No logic here."""
    path = Path(pdf_path)
    logger.info("Reading Visa statement: %s", path)
    with pdfplumber.open(path) as pdf:
        pages = [(p.extract_text() or "") for p in pdf.pages]
    logger.info("extracted %d pages from %s", len(pages), path.name) 
    return pages
