import io
import logging

import pandas as pd
import pdfplumber

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    pages = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text(layout=True, x_tolerance=3, y_tolerance=3)
            if text:
                pages.append(f"--- Page {i+1} ---\n{text}")
            logger.info('*' * 100)
            logger.info(text)
            logger.info('*' * 100)

    if not pages:
        raise ValueError("No text could be extracted — may be a scanned PDF")
    
    return "\n\n".join(pages)


def extract_text_from_csv(file_bytes: bytes) -> str:
    """Convert CSV to a plain-text table representation for LLM extraction."""
    df = pd.read_csv(io.BytesIO(file_bytes))
    return df.to_string(index=False)
