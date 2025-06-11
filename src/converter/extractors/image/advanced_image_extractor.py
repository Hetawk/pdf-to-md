"""Advanced image extraction functionality for PDF processing."""

import re
import fitz
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from ..base import BaseExtractor


class AdvancedImageExtractor(BaseExtractor):
    """Advanced image extraction with figure detection and smart naming."""

    def __init__(self, config):
        super().__init__(config)
        self.figure_counter = 0
        self.table_counter = 0
        self.diagram_counter = 0

    def extract_images_from_page(self, page, page_num: int, output_dir: Path) -> List[Dict[str, Any]]:
        """Extract images with enhanced metadata and categorization."""
        if not self.config.get('extract_images', True):
            return []

        images = []

        try:
            image_list = page.get_images()

            for img_index, img in enumerate(image_list):
                try:
                    # Get image data
                    xref = img[0]
                    pix = fitz.Pixmap(page.parent, xref)

                    if pix.n - pix.alpha < 4:  # GRAY or RGB
                        # Analyze image content to determine type
                        image_info = self._analyze_image_content(
                            page, img, pix)

                        # Generate intelligent filename
                        filename = self._generate_smart_filename(
                            image_info, page_num, img_index)

                        # Save image
                        img_path = output_dir / filename
                        pix.save(str(img_path))

                        # Extract surrounding context
                        context = self._extract_image_context(page, img)

                        images.append({
                            'filename': filename,
                            'path': str(img_path),
                            'page': page_num,
                            'index': img_index,
                            'type': image_info['type'],
                            'size': (pix.width, pix.height),
                            'bbox': img[1:5] if len(img) > 4 else None,
                            'context': context,
                            'caption': image_info.get('caption'),
                            'is_figure': image_info.get('is_figure', False),
                            'confidence': image_info.get('confidence', 0.5)
                        })

                        self.logger.debug(
                            f"Extracted {image_info['type']}: {filename}")

                    pix = None

                except Exception as e:
                    self.logger.warning(
                        f"Failed to extract image {img_index} from page {page_num}: {e}")
                    continue

        except Exception as e:
            self.logger.error(
                f"Error during advanced image extraction on page {page_num}: {e}")

        return images

    def _analyze_image_content(self, page, img, pix) -> Dict[str, Any]:
        """Analyze image content to determine type and characteristics."""
        width, height = pix.width, pix.height
        aspect_ratio = width / height if height > 0 else 1

        # Get image position on page
        bbox = img[1:5] if len(img) > 4 else None

        # Extract nearby text for context
        nearby_text = self._extract_nearby_text(page, bbox) if bbox else ""

        # Determine image type based on various factors
        image_type = "image"
        confidence = 0.5
        is_figure = False
        caption = None

        # Check for figure indicators
        if re.search(r'\bfig\.?\s*\d+|figure\s*\d+', nearby_text.lower()):
            image_type = "figure"
            is_figure = True
            confidence = 0.9
            self.figure_counter += 1
            caption = self._extract_figure_caption(nearby_text)

        # Check for table/chart indicators
        elif re.search(r'\btable\s*\d+|chart|graph', nearby_text.lower()):
            image_type = "table_image"
            confidence = 0.8
            self.table_counter += 1

        # Check for diagram indicators
        elif re.search(r'diagram|flowchart|schema|architecture', nearby_text.lower()):
            image_type = "diagram"
            confidence = 0.8
            self.diagram_counter += 1

        # Check aspect ratio patterns
        elif aspect_ratio > 2.0:  # Wide images often charts/graphs
            image_type = "chart"
            confidence = 0.6

        elif 0.8 <= aspect_ratio <= 1.2:  # Square images often diagrams
            image_type = "diagram"
            confidence = 0.6

        # Check size patterns
        elif width < 100 or height < 100:  # Small images often icons/logos
            image_type = "icon"
            confidence = 0.7

        return {
            'type': image_type,
            'confidence': confidence,
            'is_figure': is_figure,
            'caption': caption,
            'aspect_ratio': aspect_ratio,
            'nearby_text': nearby_text[:200]  # First 200 chars
        }

    def _generate_smart_filename(self, image_info: Dict, page_num: int, img_index: int) -> str:
        """Generate intelligent filename based on image analysis."""
        image_type = image_info['type']

        if image_type == "figure":
            base_name = f"figure_{self.figure_counter}_page_{page_num}"
        elif image_type == "table_image":
            base_name = f"table_{self.table_counter}_page_{page_num}"
        elif image_type == "diagram":
            base_name = f"diagram_{self.diagram_counter}_page_{page_num}"
        elif image_type == "chart":
            base_name = f"chart_{page_num}_{img_index}"
        else:
            base_name = f"image_{page_num}_{img_index}"

        return f"{base_name}.png"

    def _extract_nearby_text(self, page, bbox: Tuple[float, float, float, float], radius: float = 50) -> str:
        """Extract text near an image for context analysis."""
        if not bbox:
            return ""

        x1, y1, x2, y2 = bbox

        # Expand search area
        search_bbox = (
            x1 - radius, y1 - radius,
            x2 + radius, y2 + radius
        )

        nearby_text = []
        blocks = page.get_text("dict")

        for block in blocks.get("blocks", []):
            if "lines" in block:
                block_bbox = block["bbox"]

                # Check if block is near the image
                if self._bbox_intersects(block_bbox, search_bbox):
                    for line in block["lines"]:
                        for span in line["spans"]:
                            nearby_text.append(span["text"])

        return " ".join(nearby_text)

    def _extract_figure_caption(self, text: str) -> Optional[str]:
        """Extract figure caption from nearby text."""
        # Look for caption patterns
        patterns = [
            r'fig\.?\s*\d+[:.]\s*([^.]+)',
            r'figure\s*\d+[:.]\s*([^.]+)',
            r'caption[:.]\s*([^.]+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                return match.group(1).strip()

        return None

    def _extract_image_context(self, page, img) -> Dict[str, Any]:
        """Extract contextual information about the image."""
        bbox = img[1:5] if len(img) > 4 else None

        if not bbox:
            return {}

        # Look for preceding and following text
        preceding_text = self._extract_nearby_text(page, bbox, 100)

        return {
            'preceding_text': preceding_text[:500],  # Limit length
            'bbox': bbox,
            'page_position': self._describe_position(bbox, page.rect)
        }

    def _describe_position(self, bbox: Tuple, page_rect) -> str:
        """Describe the position of an element on the page."""
        x1, y1, x2, y2 = bbox
        page_width = page_rect.width
        page_height = page_rect.height

        # Determine horizontal position
        center_x = (x1 + x2) / 2
        if center_x < page_width * 0.33:
            h_pos = "left"
        elif center_x > page_width * 0.67:
            h_pos = "right"
        else:
            h_pos = "center"

        # Determine vertical position
        center_y = (y1 + y2) / 2
        if center_y < page_height * 0.33:
            v_pos = "top"
        elif center_y > page_height * 0.67:
            v_pos = "bottom"
        else:
            v_pos = "middle"

        return f"{v_pos}-{h_pos}"

    def _bbox_intersects(self, bbox1: Tuple, bbox2: Tuple) -> bool:
        """Check if two bounding boxes intersect."""
        x1, y1, x2, y2 = bbox1
        x3, y3, x4, y4 = bbox2

        return not (x2 < x3 or x1 > x4 or y2 < y3 or y1 > y4)
