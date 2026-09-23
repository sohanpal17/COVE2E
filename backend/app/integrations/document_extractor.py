"""Text extraction for uploaded files (PDF / text). Images are accepted but OCR is
not bundled; such files are classified from their file name and flagged for review."""
import io
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

TEXT_MIME = {"text/plain", "text/markdown", "application/json", "text/csv"}
PDF_MIME = {"application/pdf"}
IMAGE_MIME = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
ALLOWED_MIME = TEXT_MIME | PDF_MIME | IMAGE_MIME
ALLOWED_EXT = {".pdf", ".txt", ".md", ".json", ".csv", ".png", ".jpg", ".jpeg", ".webp"}


def extract_text(content: bytes, mime_type: str, file_name: str) -> Tuple[str, str]:
    """Return (text, extraction_method)."""
    lower = file_name.lower()
    if mime_type in PDF_MIME or lower.endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content))
            pages = [(page.extract_text() or "") for page in reader.pages]
            text = "\n".join(pages).strip()
            if text:
                return text, "pypdf"
            return "", "pdf-no-text-layer"
        except Exception as exc:  # pragma: no cover
            logger.warning("PDF extraction failed for %s: %s", file_name, exc)
            return "", "pdf-error"
    if mime_type in IMAGE_MIME or lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
        return "", "image-no-ocr"
    try:
        return content.decode("utf-8", errors="ignore").strip(), "plain-text"
    except Exception:  # pragma: no cover
        return "", "decode-error"
