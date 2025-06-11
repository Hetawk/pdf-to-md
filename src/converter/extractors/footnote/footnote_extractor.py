"""Footnote extraction functionality for PDF processing."""

import re
from typing import List, Dict, Any

from ..base import BaseExtractor


class FootnoteExtractor(BaseExtractor):
    """Extract and process footnotes and endnotes."""

    def __init__(self, config):
        super().__init__(config)
        self.footnote_markers = {}

    def extract_footnotes_from_page(self, page, page_num: int) -> List[Dict[str, Any]]:
        """Extract footnotes with their markers and content."""
        footnotes = []

        try:
            blocks = page.get_text("dict")

            # Find footnote markers in main text
            markers = self._find_footnote_markers(blocks)

            # Find footnote content (usually at bottom of page or in smaller font)
            content = self._find_footnote_content(blocks)

            # Match markers with content
            matched_footnotes = self._match_markers_with_content(
                markers, content, page_num)
            footnotes.extend(matched_footnotes)

        except Exception as e:
            self.logger.warning(
                f"Failed to extract footnotes from page {page_num}: {e}")

        return footnotes

    def _find_footnote_markers(self, blocks: Dict) -> List[Dict]:
        """Find footnote markers in the main text."""
        markers = []

        for block in blocks.get("blocks", []):
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"]

                        # Look for superscript numbers or symbols
                        if span.get("flags", 0) & 2**4:  # Superscript flag
                            if re.match(r'^\d+$', text.strip()):
                                markers.append({
                                    'number': int(text.strip()),
                                    'bbox': span["bbox"],
                                    'text': text
                                })

        return markers

    def _find_footnote_content(self, blocks: Dict) -> List[Dict]:
        """Find footnote content (usually smaller font at bottom)."""
        content = []

        for block in blocks.get("blocks", []):
            if "lines" in block:
                block_text = ""
                avg_font_size = 0
                font_count = 0

                for line in block["lines"]:
                    for span in line["spans"]:
                        block_text += span["text"]
                        avg_font_size += span.get("size", 0)
                        font_count += 1

                if font_count > 0:
                    avg_font_size /= font_count

                # Check if this looks like footnote content
                if (avg_font_size < 10 and  # Small font
                    # Starts with number
                    re.match(r'^\d+', block_text.strip()) and
                        len(block_text.strip()) > 20):  # Has substantial content

                    content.append({
                        'text': block_text.strip(),
                        'bbox': block["bbox"],
                        'font_size': avg_font_size
                    })

        return content

    def _match_markers_with_content(self, markers: List[Dict], content: List[Dict], page_num: int) -> List[Dict]:
        """Match footnote markers with their content."""
        footnotes = []

        for marker in markers:
            marker_num = marker['number']

            # Find matching content
            for item in content:
                if item['text'].startswith(str(marker_num)):
                    footnotes.append({
                        'number': marker_num,
                        'marker_bbox': marker['bbox'],
                        'content_bbox': item['bbox'],
                        'content': item['text'],
                        'page': page_num
                    })
                    break

        return footnotes
