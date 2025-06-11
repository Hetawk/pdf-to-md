"""OCR extraction functionality for PDF processing."""

import re
import fitz
from typing import Optional, Tuple

from ..base import BaseExtractor


class OCRExtractor(BaseExtractor):
    """Handle OCR for scanned pages and image-based content."""

    def __init__(self, config):
        super().__init__(config)
        self.ocr_engine = self._initialize_ocr_engine()

    def _initialize_ocr_engine(self):
        """Initialize OCR engine (Tesseract)."""
        try:
            import pytesseract
            return pytesseract
        except ImportError:
            self.logger.warning(
                "Tesseract not available. OCR functionality disabled.")
            return None

    def detect_scanned_page(self, page) -> bool:
        """Detect if a page is likely scanned (image-only)."""
        try:
            # Get text content
            text = page.get_text().strip()

            # Get images
            images = page.get_images()

            # If page has very little text but large images, likely scanned
            if len(text) < 50 and len(images) > 0:
                # Check if images cover most of the page
                page_area = page.rect.width * page.rect.height
                image_area = 0

                for img in images:
                    if len(img) > 4:
                        bbox = img[1:5]
                        img_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
                        image_area += img_area

                coverage = image_area / page_area if page_area > 0 else 0
                return coverage > 0.7  # 70% image coverage suggests scanned page

        except Exception as e:
            self.logger.warning(f"Failed to detect if page is scanned: {e}")

        return False

    def extract_text_from_scanned_page(self, page, page_num: int, language: str = 'eng') -> str:
        """Extract text from a scanned page using OCR."""
        if not self.ocr_engine:
            return ""

        try:
            # Convert page to image
            # 2x zoom for better OCR
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_data = pix.tobytes("png")

            # Configure OCR
            # Page segmentation mode 1 (automatic with OSD)
            config = f'--psm 1 -l {language}'

            # Run OCR
            text = self.ocr_engine.image_to_string(img_data, config=config)

            # Clean up OCR output
            cleaned_text = self._clean_ocr_text(text)

            self.logger.info(
                f"OCR extracted {len(cleaned_text)} characters from page {page_num}")

            return cleaned_text

        except Exception as e:
            self.logger.warning(f"OCR failed on page {page_num}: {e}")
            return ""

    def _clean_ocr_text(self, text: str) -> str:
        """Clean and improve OCR output."""
        if not text:
            return ""

        # Remove excessive whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)

        # Fix common OCR errors
        ocr_fixes = [
            (r'\b1\b(?=\s*[a-z])', 'I'),  # 1 -> I
            (r'\b0\b(?=\s*[a-z])', 'O'),  # 0 -> O
            (r'rn', 'm'),  # rn -> m
            (r'cl', 'd'),   # cl -> d (sometimes)
        ]

        for pattern, replacement in ocr_fixes:
            text = re.sub(pattern, replacement, text)

        return text.strip()

    def extract_table_from_image(self, page, table_bbox: Tuple[float, float, float, float]) -> Optional[str]:
        """Extract table structure from an image region using OCR."""
        if not self.ocr_engine:
            return None

        try:
            # Extract the table region as image
            rect = fitz.Rect(table_bbox)
            # High resolution for tables
            pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=rect)
            img_data = pix.tobytes("png")

            # Use table-specific OCR configuration
            config = '--psm 6'  # Uniform block of text

            text = self.ocr_engine.image_to_string(img_data, config=config)

            # Convert to markdown table format
            table_markdown = self._ocr_text_to_table(text)

            return table_markdown

        except Exception as e:
            self.logger.warning(f"Table OCR failed: {e}")
            return None

    def _ocr_text_to_table(self, text: str) -> Optional[str]:
        """Convert OCR text output to markdown table format."""
        if not text.strip():
            return None

        lines = [line.strip() for line in text.split('\n') if line.strip()]

        if len(lines) < 2:
            return None

        # Try to detect column structure
        table_lines = []
        for line in lines:
            # Split on multiple spaces or common separators
            columns = re.split(r'\s{2,}|\t+|\|', line)
            if len(columns) >= 2:
                table_lines.append([col.strip() for col in columns])

        if len(table_lines) < 2:
            return None

        # Normalize column count
        max_cols = max(len(row) for row in table_lines)
        normalized_rows = []
        for row in table_lines:
            while len(row) < max_cols:
                row.append("")
            normalized_rows.append(row[:max_cols])

        # Build markdown table
        markdown_lines = ["**OCR Table**", ""]

        # Header
        header = normalized_rows[0]
        markdown_lines.append("| " + " | ".join(header) + " |")
        markdown_lines.append("| " + " | ".join(["---"] * len(header)) + " |")

        # Data rows
        for row in normalized_rows[1:]:
            cleaned_row = [cell.replace('|', '\\|') for cell in row]
            markdown_lines.append("| " + " | ".join(cleaned_row) + " |")

        return "\n".join(markdown_lines)
