"""Text extraction functionality for PDF processing."""

import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import fitz

from ..base import BaseExtractor


class TextExtractor(BaseExtractor):
    """Extract and process text content from PDF pages."""

    def __init__(self, config):
        super().__init__(config)
        self.font_sizes = {}
        self.common_fonts = {}
        self.font_hierarchy = {}

    def analyze_document_structure(self, doc):
        """Analyze the document to identify heading patterns."""
        font_sizes = {}

        for page_num in range(len(doc)):
            page = doc[page_num]
            blocks = page.get_text("dict")

            for block in blocks["blocks"]:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            font_size = span["size"]
                            font_flags = span["flags"]
                            text = span["text"].strip()

                            if text and len(text) > 3:
                                key = (font_size, font_flags)
                                if key not in font_sizes:
                                    font_sizes[key] = []
                                font_sizes[key].append(text)

        # Sort font sizes to determine hierarchy
        sorted_fonts = sorted(
            font_sizes.keys(), key=lambda x: x[0], reverse=True)
        self.font_hierarchy = {font: i+1 for i,
                               font in enumerate(sorted_fonts[:6])}

    def clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove hyphenation at line breaks
        text = re.sub(r'-\s+', '', text)
        return text.strip()

    def handle_mathematical_content(self, text: str) -> str:
        """Preserve mathematical notation and formulas."""
        # Detect LaTeX-like math expressions
        math_patterns = [
            (r'\$([^$]+)\$', r'$\1$'),  # Inline math
            (r'\\begin\{([^}]+)\}(.*?)\\end\{\1\}',
             r'```math\n\2\n```'),  # Block math
            (r'([α-ωΑ-Ω])', r'$\1$'),  # Greek letters
            (r'([∑∏∫∂∇±×÷≤≥≠≈∞])', r'$\1$'),  # Math symbols
        ]

        for pattern, replacement in math_patterns:
            text = re.sub(pattern, replacement, text, flags=re.DOTALL)

        return text

    def is_likely_heading(self, text: str, font_info: Tuple[float, int]) -> bool:
        """Determine if text is likely a heading."""
        if len(text) > 200:  # Too long for a heading
            return False

        # Check for common heading patterns
        heading_patterns = [
            r'^\d+\.?\s+[A-Z]',  # Numbered sections
            r'^[A-Z][A-Z\s]+$',  # ALL CAPS
            r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*$',  # Title Case
            r'^\d+\.\d+',  # Subsection numbering
            r'^Abstract$|^Introduction$|^Conclusion$|^References$',  # Common sections
        ]

        for pattern in heading_patterns:
            if re.match(pattern, text):
                return True

        return False

    def determine_heading_level(self, font_info: Tuple[float, int]) -> Optional[int]:
        """Determine heading level based on font characteristics."""
        if font_info in self.font_hierarchy:
            return self.font_hierarchy[font_info]
        return None

    def extract_text(self, page) -> List[str]:
        """Extract text from a page with enhanced formatting."""
        content = []

        try:
            blocks = page.get_text("dict")

            for block in blocks["blocks"]:
                if "lines" in block:
                    for line in block["lines"]:
                        line_text = ""
                        for span in line["spans"]:
                            text = span["text"]
                            font_size = span["size"]
                            font_flags = span["flags"]

                            # Clean and process text
                            text = self.clean_text(text)
                            text = self.handle_mathematical_content(text)

                            if text:
                                font_info = (font_size, font_flags)

                                # Check if this is a heading
                                if self.is_likely_heading(text, font_info):
                                    heading_level = self.determine_heading_level(
                                        font_info)
                                    if heading_level and heading_level <= 6:
                                        text = f"{'#' * heading_level} {text}"

                                line_text += text + " "

                        if line_text.strip():
                            content.append(line_text.strip())

        except Exception as e:
            self.logger.error(f"Error extracting text: {e}")

        return content

    def extract_paragraphs(self, page) -> List[str]:
        """Extract paragraphs with proper formatting."""
        paragraphs = []
        current_paragraph = []

        try:
            text_blocks = page.get_text("dict")["blocks"]

            for block in text_blocks:
                if "lines" in block:
                    block_text = ""
                    for line in block["lines"]:
                        for span in line["spans"]:
                            text = span["text"].strip()
                            if text:
                                block_text += text + " "

                    if block_text.strip():
                        # Clean the text
                        block_text = self.clean_text(block_text)
                        block_text = self.handle_mathematical_content(
                            block_text)

                        # Check if this starts a new paragraph
                        if block_text.endswith('.') or len(current_paragraph) == 0:
                            current_paragraph.append(block_text)
                            paragraphs.append(' '.join(current_paragraph))
                            current_paragraph = []
                        else:
                            current_paragraph.append(block_text)

            # Add any remaining content
            if current_paragraph:
                paragraphs.append(' '.join(current_paragraph))

        except Exception as e:
            self.logger.error(f"Error extracting paragraphs: {e}")

        return paragraphs

    def handle_multi_column_text(self, page, blocks: Dict) -> List[str]:
        """Handle multi-column text layout detection and processing."""
        try:
            # Detect if page has multi-column layout
            if not self._detect_multi_column_layout(blocks):
                # Single column - use regular processing
                return self._extract_single_column_text(blocks)

            # Multi-column processing
            return self._extract_multi_column_text(blocks)

        except Exception as e:
            self.logger.warning(f"Multi-column text handling failed: {e}")
            # Fallback to simple text extraction
            return [page.get_text()]

    def _detect_multi_column_layout(self, blocks: Dict) -> bool:
        """Detect if the page has a multi-column layout."""
        try:
            # Get text blocks with their positions
            text_blocks = []
            for block in blocks.get("blocks", []):
                if "lines" in block and block["lines"]:
                    bbox = block["bbox"]
                    text = self._extract_block_text(block)
                    if text.strip():
                        text_blocks.append({
                            'text': text,
                            'bbox': bbox,
                            'x_center': (bbox[0] + bbox[2]) / 2
                        })

            if len(text_blocks) < 4:
                return False

            # Group blocks by their x-center positions
            x_positions = [block['x_center'] for block in text_blocks]
            x_positions.sort()

            # Look for distinct column boundaries
            gaps = []
            for i in range(1, len(x_positions)):
                gap = x_positions[i] - x_positions[i-1]
                if gap > 50:  # Significant gap suggests column boundary
                    gaps.append(gap)

            # If we have large gaps, likely multi-column
            return len(gaps) >= 1 and max(gaps) > 100

        except Exception:
            return False

    def _extract_single_column_text(self, blocks: Dict) -> List[str]:
        """Extract text from single-column layout."""
        paragraphs = []
        current_paragraph = []

        try:
            for block in blocks.get("blocks", []):
                if "lines" in block:
                    block_text = ""
                    for line in block["lines"]:
                        for span in line["spans"]:
                            text = span["text"].strip()
                            if text:
                                block_text += text + " "

                    if block_text.strip():
                        # Clean the text
                        block_text = self.clean_text(block_text)
                        block_text = self.handle_mathematical_content(
                            block_text)

                        # Check if this starts a new paragraph
                        if block_text.endswith('.') or len(current_paragraph) == 0:
                            current_paragraph.append(block_text)
                            paragraphs.append(' '.join(current_paragraph))
                            current_paragraph = []
                        else:
                            current_paragraph.append(block_text)

            # Add any remaining content
            if current_paragraph:
                paragraphs.append(' '.join(current_paragraph))

        except Exception as e:
            self.logger.error(f"Error extracting single column text: {e}")

        return paragraphs

    def _extract_multi_column_text(self, blocks: Dict) -> List[str]:
        """Extract text from multi-column layout."""
        try:
            # Group blocks by columns first
            columns = self._group_blocks_by_columns(blocks)

            all_paragraphs = []

            # Process each column
            for column_blocks in columns:
                column_dict = {"blocks": column_blocks}
                column_paragraphs = self._extract_single_column_text(
                    column_dict)
                all_paragraphs.extend(column_paragraphs)

            return all_paragraphs

        except Exception as e:
            self.logger.error(f"Error extracting multi-column text: {e}")
            return self._extract_single_column_text(blocks)

    def _group_blocks_by_columns(self, blocks: Dict) -> List[List[Dict]]:
        """Group text blocks by their column positions."""
        try:
            # Get all text blocks with positions
            text_blocks = []
            for block in blocks.get("blocks", []):
                if "lines" in block and block["lines"]:
                    text_blocks.append(block)

            if not text_blocks:
                return []

            # Sort blocks by their x-position (left to right)
            text_blocks.sort(key=lambda b: b["bbox"][0])

            # Group into columns based on x-position clustering
            columns = []
            current_column = []
            current_x_range = None

            for block in text_blocks:
                block_x_center = (block["bbox"][0] + block["bbox"][2]) / 2

                if current_x_range is None:
                    # First block starts first column
                    current_x_range = [block["bbox"][0], block["bbox"][2]]
                    current_column = [block]
                else:
                    # Check if block belongs to current column
                    if (block["bbox"][0] <= current_x_range[1] + 50 and  # Some overlap tolerance
                            block["bbox"][2] >= current_x_range[0] - 50):
                        # Belongs to current column
                        current_column.append(block)
                        # Update x-range
                        current_x_range[0] = min(
                            current_x_range[0], block["bbox"][0])
                        current_x_range[1] = max(
                            current_x_range[1], block["bbox"][2])
                    else:
                        # Start new column
                        if current_column:
                            columns.append(current_column)
                        current_column = [block]
                        current_x_range = [block["bbox"][0], block["bbox"][2]]

            # Add last column
            if current_column:
                columns.append(current_column)

            # Sort blocks within each column by y-position (top to bottom)
            for column in columns:
                column.sort(key=lambda b: b["bbox"][1])

            return columns

        except Exception as e:
            self.logger.error(f"Error grouping blocks by columns: {e}")
            return [blocks.get("blocks", [])]

    def _extract_block_text(self, block: Dict) -> str:
        """Extract text from a single block."""
        text = ""
        try:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text += span.get("text", "") + " "
        except Exception:
            pass
        return text.strip()
