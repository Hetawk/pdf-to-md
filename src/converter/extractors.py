"""Content extraction functionality for PDF processing."""

import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import fitz


class BaseExtractor:
    """Base class for content extractors."""

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)


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
            level = self.font_hierarchy[font_info]
            return min(level, 6)  # Markdown supports up to 6 levels
        return None

    def detect_multi_column_layout(self, page) -> bool:
        """Detect if page has multi-column layout."""
        blocks = page.get_text("dict")
        page_width = page.rect.width

        # Analyze text block positions
        left_blocks = []
        right_blocks = []

        for block in blocks["blocks"]:
            if "lines" in block:
                bbox = block["bbox"]
                block_center_x = (bbox[0] + bbox[2]) / 2

                if block_center_x < page_width * 0.45:  # Left column
                    left_blocks.append(block)
                elif block_center_x > page_width * 0.55:  # Right column
                    right_blocks.append(block)

        # If we have significant content in both columns
        return len(left_blocks) > 3 and len(right_blocks) > 3

    def handle_multi_column_text(self, page) -> Optional[List[str]]:
        """Handle multi-column text extraction properly."""
        if not self.detect_multi_column_layout(page):
            return None

        blocks = page.get_text("dict")
        page_width = page.rect.width

        left_column = []
        right_column = []

        for block in blocks["blocks"]:
            if "lines" in block:
                bbox = block["bbox"]
                block_center_x = (bbox[0] + bbox[2]) / 2

                block_text = ""
                for line in block["lines"]:
                    for span in line["spans"]:
                        block_text += span["text"]

                block_text = self.clean_text(block_text)

                if block_text:
                    if block_center_x < page_width * 0.45:
                        # Store with y-position
                        left_column.append((bbox[1], block_text))
                    elif block_center_x > page_width * 0.55:
                        right_column.append((bbox[1], block_text))

        # Sort by y-position
        left_column.sort()
        right_column.sort()

        # Combine columns properly
        combined_text = []
        combined_text.extend([text for _, text in left_column])
        combined_text.extend([text for _, text in right_column])

        return combined_text

    def detect_footnotes_and_references(self, page) -> Tuple[List[str], List[str]]:
        """Detect footnotes and references on the page."""
        blocks = page.get_text("dict")
        footnotes = []
        references = []

        for block in blocks["blocks"]:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"].strip()
                        font_size = span["size"]

                        # Detect footnotes (small font size, starts with number)
                        if font_size < 9 and re.match(r'^\d+\s', text):
                            footnotes.append(text)

                        # Detect references (common patterns)
                        if re.search(r'\[\d+\]|\(\d{4}\)|doi:|arXiv:', text):
                            references.append(text)

        return footnotes, references


class ImageExtractor(BaseExtractor):
    """Extract images from PDF pages."""

    def extract_images(self, doc, output_dir: Path) -> List[str]:
        """Extract all images from the PDF document."""
        if not self.config.get('extract_images', True):
            return []

        images_dir = output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        image_refs = []
        image_count = 0

        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images()

            for img_index, img in enumerate(image_list):
                try:
                    # Get image data
                    xref = img[0]
                    pix = fitz.Pixmap(doc, xref)

                    # Skip images that are too small (likely artifacts)
                    if pix.width < 50 or pix.height < 50:
                        pix = None
                        continue

                    # Generate filename
                    image_filename = f"image_{page_num+1}_{img_index+1}.png"
                    image_path = images_dir / image_filename

                    # Save image
                    if pix.n - pix.alpha < 4:  # GRAY or RGB
                        pix.save(str(image_path))
                    else:  # CMYK: convert to RGB first
                        pix1 = fitz.Pixmap(fitz.csRGB, pix)
                        pix1.save(str(image_path))
                        pix1 = None

                    # Store relative path for markdown
                    relative_path = f"images/{image_filename}"
                    image_refs.append(relative_path)
                    image_count += 1

                    self.logger.debug(f"Extracted image: {image_filename}")
                    pix = None

                except Exception as e:
                    self.logger.warning(
                        f"Failed to extract image {img_index} from page {page_num}: {e}")
                    continue

        self.logger.info(f"Extracted {image_count} images")
        return image_refs


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


class LinkExtractor(BaseExtractor):
    """Extract and process links, cross-references, and citations."""

    def __init__(self, config):
        super().__init__(config)
        self.internal_refs = {}
        self.external_links = []
        self.citations = []

    def extract_links_from_page(self, page, page_num: int) -> Dict[str, List[Dict]]:
        """Extract various types of links and references."""
        result = {
            'external_links': [],
            'internal_refs': [],
            'citations': [],
            'footnotes': []
        }

        try:
            # Extract hyperlinks
            links = page.get_links()
            for link in links:
                link_info = self._analyze_link(link, page_num)
                if link_info['type'] == 'external':
                    result['external_links'].append(link_info)
                else:
                    result['internal_refs'].append(link_info)

            # Extract text-based references
            text_refs = self._extract_text_references(page, page_num)
            result['citations'].extend(text_refs['citations'])
            result['footnotes'].extend(text_refs['footnotes'])

        except Exception as e:
            self.logger.warning(
                f"Failed to extract links from page {page_num}: {e}")

        return result

    def _analyze_link(self, link: Dict, page_num: int) -> Dict[str, Any]:
        """Analyze a link to determine its type and characteristics."""
        uri = link.get('uri', '')
        bbox = link.get('from', {})

        link_type = 'internal'
        if uri.startswith(('http://', 'https://', 'ftp://')):
            link_type = 'external'
        elif uri.startswith('mailto:'):
            link_type = 'email'
        elif uri.startswith('#'):
            link_type = 'anchor'

        return {
            'type': link_type,
            'uri': uri,
            'page': page_num,
            'bbox': bbox,
            'text': self._extract_link_text(bbox) if bbox else '',
            'domain': self._extract_domain(uri) if link_type == 'external' else None
        }

    def _extract_text_references(self, page, page_num: int) -> Dict[str, List[Dict]]:
        """Extract citations and footnotes from text."""
        text = page.get_text()

        citations = []
        footnotes = []

        # Citation patterns
        citation_patterns = [
            r'\[(\d+(?:,\s*\d+)*)\]',  # [1], [1,2,3]
            # (Smith et al., 2020)
            r'\(([A-Za-z]+(?:\s+et\s+al\.?)?,?\s+\d{4}[a-z]?)\)',
            r'\((\d{4})\)',  # (2020)
        ]

        for pattern in citation_patterns:
            for match in re.finditer(pattern, text):
                citations.append({
                    'text': match.group(0),
                    'reference': match.group(1),
                    'page': page_num,
                    'position': match.start(),
                    'type': 'citation'
                })

        # Footnote patterns
        footnote_patterns = [
            r'(\d+)\s*([^\n]+)',  # Footnote text
        ]

        lines = text.split('\n')
        for line_num, line in enumerate(lines):
            if self._looks_like_footnote(line):
                footnotes.append({
                    'text': line.strip(),
                    'page': page_num,
                    'line': line_num,
                    'type': 'footnote'
                })

        return {'citations': citations, 'footnotes': footnotes}

    def _extract_link_text(self, bbox: Dict) -> str:
        """Extract the text content of a link."""
        # This would need access to the page text within the bbox
        return ""  # Placeholder

    def _extract_domain(self, uri: str) -> Optional[str]:
        """Extract domain from URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(uri)
            return parsed.netloc
        except:
            return None

    def _looks_like_footnote(self, line: str) -> bool:
        """Check if a line looks like a footnote."""
        line = line.strip()
        if len(line) < 10:
            return False

        # Check if starts with number and has reasonable content
        return bool(re.match(r'^\d+\s+[A-Za-z]', line))


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


class TableExtractor(BaseExtractor):
    """Advanced table extraction with support for complex layouts and spanning cells."""

    def __init__(self, config):
        super().__init__(config)
        self.table_strategies = ['bbox_analysis', 'text_alignment', 'hybrid']
        self.min_table_confidence = 0.7

    def extract_tables_from_page(self, page, page_num: int) -> List[Dict[str, Any]]:
        """Extract tables from a page with enhanced analysis."""
        if not self.config.get('extract_tables', True):
            return []

        tables = []

        try:
            # Strategy 1: Bounding box analysis for structured tables
            bbox_tables = self._extract_bbox_tables(page, page_num)
            tables.extend(bbox_tables)

            # Strategy 2: Text alignment analysis
            alignment_tables = self._extract_alignment_tables(page, page_num)
            tables.extend(alignment_tables)

            # Strategy 3: Look for explicit table markers
            marker_tables = self._extract_marked_tables(page, page_num)
            tables.extend(marker_tables)

            # Remove duplicates and low-confidence tables
            tables = self._deduplicate_and_filter_tables(tables)

        except Exception as e:
            self.logger.warning(
                f"Failed to extract tables from page {page_num}: {e}")

        return tables

    def _extract_bbox_tables(self, page, page_num: int) -> List[Dict[str, Any]]:
        """Extract tables using bounding box analysis for grid-like structures."""
        tables = []

        try:
            blocks = page.get_text("dict")

            # Group blocks by their spatial relationships
            table_regions = self._identify_grid_regions(blocks, page.rect)

            for region_idx, region in enumerate(table_regions):
                table_data = self._analyze_grid_structure(region)
                if table_data and self._validate_table_structure(table_data):
                    tables.append({
                        'type': 'bbox_grid',
                        'page': page_num,
                        'region_id': region_idx,
                        'data': table_data,
                        'confidence': self._calculate_table_confidence(table_data),
                        'bbox': self._get_region_bbox(region)
                    })

        except Exception as e:
            self.logger.warning(
                f"BBox table extraction failed on page {page_num}: {e}")

        return tables

    def _extract_alignment_tables(self, page, page_num: int) -> List[Dict[str, Any]]:
        """Extract tables using text alignment analysis."""
        tables = []

        try:
            text_lines = self._get_structured_text_lines(page)
            table_regions = self._find_aligned_text_regions(text_lines)

            for region_idx, region in enumerate(table_regions):
                table_data = self._parse_aligned_table(region)
                if table_data and len(table_data) >= 2:  # At least header + 1 row
                    tables.append({
                        'type': 'text_alignment',
                        'page': page_num,
                        'region_id': region_idx,
                        'data': table_data,
                        'confidence': self._calculate_alignment_confidence(region),
                        'bbox': self._get_text_region_bbox(region)
                    })

        except Exception as e:
            self.logger.warning(
                f"Alignment table extraction failed on page {page_num}: {e}")

        return tables

    def _extract_marked_tables(self, page, page_num: int) -> List[Dict[str, Any]]:
        """Extract tables with explicit markers (borders, separators)."""
        tables = []

        try:
            # Look for drawing elements that might be table borders
            drawings = page.get_drawings()
            lines = self._extract_table_lines(drawings)

            if lines:
                grid_structure = self._build_grid_from_lines(lines)
                if grid_structure:
                    # Get text content within grid cells
                    table_data = self._extract_text_from_grid(
                        page, grid_structure)
                    if table_data:
                        tables.append({
                            'type': 'marked_table',
                            'page': page_num,
                            'region_id': 0,
                            'data': table_data,
                            'confidence': 0.9,  # High confidence for marked tables
                            'bbox': self._get_grid_bbox(grid_structure)
                        })

        except Exception as e:
            self.logger.warning(
                f"Marked table extraction failed on page {page_num}: {e}")

        return tables

    def convert_table_to_markdown(self, table: Dict[str, Any]) -> str:
        """Convert a table structure to markdown with enhanced formatting."""
        table_data = table['data']
        if not table_data:
            return ""

        markdown_lines = []

        # Add table caption if available
        table_num = table.get('region_id', 0) + 1
        confidence = table.get('confidence', 0)
        table_type = table.get('type', 'unknown')

        markdown_lines.append(
            f"\n**Table {table_num}** *(confidence: {confidence:.2f}, type: {table_type})*")
        markdown_lines.append("")

        # Normalize table data
        max_cols = max(len(row) for row in table_data) if table_data else 0
        if max_cols == 0:
            return ""

        normalized_data = []
        for row in table_data:
            normalized_row = list(row)
            while len(normalized_row) < max_cols:
                normalized_row.append("")
            normalized_data.append(normalized_row[:max_cols])

        # Create header row
        header = normalized_data[0] if normalized_data else []
        if not any(h.strip() for h in header):
            # Generate generic column headers if first row is empty
            header = [f"Col{i+1}" for i in range(max_cols)]
            data_rows = normalized_data
        else:
            data_rows = normalized_data[1:]

        # Clean header cells
        clean_header = []
        for cell in header:
            cleaned = re.sub(r'[|\n\r]', ' ', str(cell)).strip()
            if not cleaned:
                cleaned = "Column"
            clean_header.append(cleaned)

        # Build markdown table
        markdown_lines.append("| " + " | ".join(clean_header) + " |")
        markdown_lines.append(
            "| " + " | ".join(["---"] * len(clean_header)) + " |")

        # Add data rows
        for row in data_rows:
            clean_row = []
            for cell in row:
                # Clean cell content
                cleaned = re.sub(r'[|\n\r]', ' ', str(cell)).strip()
                # Escape any remaining pipes
                cleaned = cleaned.replace('|', '\\|')
                clean_row.append(cleaned)

            markdown_lines.append("| " + " | ".join(clean_row) + " |")

        markdown_lines.append("")  # Add spacing after table

        return "\n".join(markdown_lines)

    def detect_numerical_patterns(self, text: str) -> bool:
        """Detect if text contains numerical data typical of ML results."""
        # Look for patterns common in ML papers
        patterns = [
            r'\d+\.\d+%',  # Percentages
            r'\d+\.\d+±\d+\.\d+',  # Mean ± std
            r'\d+\.\d+\s*[±]\s*\d+\.\d+',  # Mean ± std (with spaces)
            r'\d+\.\d{2,4}',  # Decimal numbers (accuracy, loss, etc.)
            r'\d+[,]\d+',  # Large numbers with commas
            r'\b\d+[kKmM]\b',  # Numbers with k/M suffixes
        ]

        for pattern in patterns:
            if re.search(pattern, text):
                return True
        return False

    # Helper methods for advanced table extraction
    def _identify_grid_regions(self, blocks: Dict, page_rect) -> List[List[Dict]]:
        """Identify regions that might contain grid-structured tables."""
        # Simplified implementation - would be more sophisticated in practice
        regions = []

        # Extract text blocks with position information
        text_blocks = []
        for block in blocks.get("blocks", []):
            if "lines" in block and block["lines"]:
                bbox = block["bbox"]
                text = self._extract_block_text(block)
                if text.strip():
                    text_blocks.append({
                        'text': text,
                        'bbox': bbox,
                        'block': block
                    })

        if len(text_blocks) < 4:  # Need minimum blocks for a table
            return regions

        # Simple grouping by y-coordinates (would be more sophisticated)
        text_blocks.sort(key=lambda b: (b['bbox'][1], b['bbox'][0]))

        current_row = []
        current_y = None
        y_tolerance = 10

        for block in text_blocks:
            block_y = block['bbox'][1]

            if current_y is None or abs(block_y - current_y) <= y_tolerance:
                current_row.append(block)
                current_y = block_y if current_y is None else current_y
            else:
                if len(current_row) >= 2:
                    regions.append([current_row])
                current_row = [block]
                current_y = block_y

        if len(current_row) >= 2:
            regions.append([current_row])

        return regions

    def _analyze_grid_structure(self, region: List[List[Dict]]) -> Optional[List[List[str]]]:
        """Analyze a region to extract grid structure."""
        if not region:
            return None

        table_data = []

        for row_blocks in region:
            # Sort blocks in row by x-coordinate
            row_blocks.sort(key=lambda b: b['bbox'][0])

            # Extract text from each cell
            row_data = []
            for block in row_blocks:
                cell_text = block['text'].strip()
                # Clean up cell text
                cell_text = re.sub(r'\s+', ' ', cell_text)
                row_data.append(cell_text)

            if row_data:  # Only add non-empty rows
                table_data.append(row_data)

        return table_data if table_data else None

    def _get_structured_text_lines(self, page) -> List[Dict]:
        """Get text lines with detailed position and formatting info."""
        lines = []
        blocks = page.get_text("dict")

        for block in blocks.get("blocks", []):
            if "lines" in block:
                for line in block["lines"]:
                    line_text = ""
                    spans_info = []
                    line_bbox = None

                    for span in line["spans"]:
                        line_text += span["text"]
                        spans_info.append({
                            'text': span["text"],
                            'font': span.get("font", ""),
                            'size': span.get("size", 0),
                            'flags': span.get("flags", 0),
                            'bbox': span["bbox"]
                        })

                        # Calculate line bbox
                        if line_bbox is None:
                            line_bbox = list(span["bbox"])
                        else:
                            line_bbox[0] = min(line_bbox[0], span["bbox"][0])
                            line_bbox[1] = min(line_bbox[1], span["bbox"][1])
                            line_bbox[2] = max(line_bbox[2], span["bbox"][2])
                            line_bbox[3] = max(line_bbox[3], span["bbox"][3])

                    if line_text.strip():
                        lines.append({
                            'text': line_text,
                            'bbox': line_bbox,
                            'spans': spans_info,
                            'block_bbox': block["bbox"]
                        })

        return lines

    def _find_aligned_text_regions(self, text_lines: List[Dict]) -> List[List[Dict]]:
        """Find regions of aligned text that might be tables."""
        if len(text_lines) < 3:
            return []

        regions = []
        current_region = []

        # Group lines that have similar structure
        for line in text_lines:
            if self._is_table_like_line(line):
                current_region.append(line)
            else:
                if len(current_region) >= 3:  # Minimum for a table
                    regions.append(current_region)
                current_region = []

        # Handle last region
        if len(current_region) >= 3:
            regions.append(current_region)

        return regions

    def _is_table_like_line(self, line: Dict) -> bool:
        """Check if a line has characteristics of a table row."""
        text = line['text'].strip()

        if not text or len(text) < 10:
            return False

        # Check for multiple segments separated by whitespace
        segments = re.split(r'\s{2,}', text)
        if len(segments) < 2:
            return False

        # Check for numerical content
        has_numbers = bool(re.search(r'\d+', text))

        # Check for consistent formatting patterns
        has_separators = bool(re.search(r'[|,\t]', text))

        return len(segments) >= 2 and (has_numbers or has_separators)

    def _parse_aligned_table(self, region: List[Dict]) -> Optional[List[List[str]]]:
        """Parse an aligned text region into table structure."""
        if not region:
            return None

        table_data = []

        for line in region:
            text = line['text'].strip()

            # Split into columns based on spacing patterns
            columns = re.split(r'\s{2,}', text)

            if len(columns) >= 2:
                # Clean up column text
                cleaned_columns = []
                for col in columns:
                    cleaned = re.sub(r'\s+', ' ', col.strip())
                    cleaned_columns.append(cleaned)
                table_data.append(cleaned_columns)

        # Normalize column count
        if table_data:
            max_cols = max(len(row) for row in table_data)
            normalized_data = []
            for row in table_data:
                while len(row) < max_cols:
                    row.append("")
                normalized_data.append(row[:max_cols])
            return normalized_data

        return None

    def _extract_table_lines(self, drawings: List) -> List[Dict]:
        """Extract lines that might be table borders."""
        lines = []

        for drawing in drawings:
            # Check if drawing contains line segments
            for item in drawing.get("items", []):
                if item[0] == "l":  # Line command
                    # Extract line coordinates
                    coords = item[1:]
                    if len(coords) >= 4:
                        lines.append({
                            'type': 'line',
                            'start': (coords[0], coords[1]),
                            'end': (coords[2], coords[3])
                        })

        return lines

    def _build_grid_from_lines(self, lines: List[Dict]) -> Optional[Dict]:
        """Build a grid structure from detected lines."""
        if not lines:
            return None

        # Group lines into horizontal and vertical
        horizontal_lines = []
        vertical_lines = []

        for line in lines:
            start = line['start']
            end = line['end']

            # Check if line is approximately horizontal or vertical
            if abs(start[1] - end[1]) < 2:  # Horizontal
                horizontal_lines.append({
                    'y': (start[1] + end[1]) / 2,
                    'x_start': min(start[0], end[0]),
                    'x_end': max(start[0], end[0])
                })
            elif abs(start[0] - end[0]) < 2:  # Vertical
                vertical_lines.append({
                    'x': (start[0] + end[0]) / 2,
                    'y_start': min(start[1], end[1]),
                    'y_end': max(start[1], end[1])
                })

        if len(horizontal_lines) < 2 or len(vertical_lines) < 2:
            return None

        # Sort lines
        horizontal_lines.sort(key=lambda l: l['y'])
        vertical_lines.sort(key=lambda l: l['x'])

        return {
            'horizontal': horizontal_lines,
            'vertical': vertical_lines
        }

    def _extract_text_from_grid(self, page, grid_structure: Dict) -> Optional[List[List[str]]]:
        """Extract text content from within grid cells."""
        if not grid_structure:
            return None

        h_lines = grid_structure['horizontal']
        v_lines = grid_structure['vertical']

        table_data = []

        # For each row between horizontal lines
        for i in range(len(h_lines) - 1):
            row_data = []
            y_top = h_lines[i]['y']
            y_bottom = h_lines[i + 1]['y']

            # For each column between vertical lines
            for j in range(len(v_lines) - 1):
                x_left = v_lines[j]['x']
                x_right = v_lines[j + 1]['x']

                # Extract text within this cell
                cell_text = self._extract_text_in_bbox(
                    page, (x_left, y_top, x_right, y_bottom))
                row_data.append(cell_text.strip())

            if any(cell.strip() for cell in row_data):  # Only add non-empty rows
                table_data.append(row_data)

        return table_data if table_data else None

    def _extract_text_in_bbox(self, page, bbox: Tuple[float, float, float, float]) -> str:
        """Extract text within a specific bounding box."""
        x1, y1, x2, y2 = bbox

        # Get all text in the page
        text_instances = page.get_text("dict")

        extracted_text = []

        for block in text_instances.get("blocks", []):
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        span_bbox = span["bbox"]

                        # Check if span is within the target bbox
                        if (span_bbox[0] >= x1 and span_bbox[1] >= y1 and
                                span_bbox[2] <= x2 and span_bbox[3] <= y2):
                            extracted_text.append(span["text"])

        return " ".join(extracted_text)

    def _validate_table_structure(self, table_data: List[List[str]]) -> bool:
        """Validate that the extracted data looks like a proper table."""
        if not table_data or len(table_data) < 2:
            return False

        # Check if rows have consistent column counts (with some tolerance)
        col_counts = [len(row) for row in table_data]
        max_cols = max(col_counts)
        min_cols = min(col_counts)

        # Allow some variation in column count
        if max_cols - min_cols > 2:
            return False

        # Check if table contains meaningful content
        total_cells = sum(col_counts)
        non_empty_cells = sum(
            1 for row in table_data for cell in row if cell.strip())

        if non_empty_cells / total_cells < 0.5:  # At least 50% of cells should have content
            return False

        # Check for numerical content (tables often contain numbers)
        numerical_cells = sum(1 for row in table_data for cell in row
                              if re.search(r'\d', cell))

        if numerical_cells < 2:  # Should have at least some numerical content
            return False

        return True

    def _calculate_table_confidence(self, table_data: List[List[str]]) -> float:
        """Calculate confidence score for extracted table."""
        if not table_data:
            return 0.0

        score = 0.0

        # Size factor
        total_cells = sum(len(row) for row in table_data)
        if total_cells >= 6:
            score += 0.2
        if len(table_data) >= 3:
            score += 0.2

        # Content consistency
        col_counts = [len(row) for row in table_data]
        if max(col_counts) - min(col_counts) <= 1:
            score += 0.3

        # Numerical content
        numerical_cells = sum(1 for row in table_data for cell in row
                              if re.search(r'\d+\.\d+|\d+%', cell))
        if numerical_cells > total_cells * 0.3:
            score += 0.3

        return min(score, 1.0)

    def _calculate_alignment_confidence(self, region: List[Dict]) -> float:
        """Calculate confidence for alignment-based table."""
        if not region:
            return 0.0

        # Check alignment consistency
        x_positions = []
        for line in region:
            for span in line.get('spans', []):
                x_positions.append(span['bbox'][0])

        # Look for consistent column positions
        unique_positions = sorted(set(round(x, -1) for x in x_positions))

        if len(unique_positions) >= 2:
            return min(0.8, 0.4 + 0.1 * len(unique_positions))

        return 0.4

    def _deduplicate_and_filter_tables(self, tables: List[Dict]) -> List[Dict]:
        """Remove duplicate tables and filter by confidence."""
        if not tables:
            return []

        # Sort by confidence
        tables.sort(key=lambda t: t['confidence'], reverse=True)

        # Remove low-confidence tables
        filtered_tables = [
            t for t in tables if t['confidence'] >= self.min_table_confidence]

        # Remove overlapping tables (keep highest confidence)
        final_tables = []
        for table in filtered_tables:
            bbox = table['bbox']
            overlaps = False

            for existing in final_tables:
                if self._bboxes_overlap(bbox, existing['bbox']):
                    overlaps = True
                    break

            if not overlaps:
                final_tables.append(table)

        return final_tables

    def _bboxes_overlap(self, bbox1: Tuple, bbox2: Tuple) -> bool:
        """Check if two bounding boxes overlap significantly."""
        x1, y1, x2, y2 = bbox1
        x3, y3, x4, y4 = bbox2

        # Calculate overlap area
        overlap_x = max(0, min(x2, x4) - max(x1, x3))
        overlap_y = max(0, min(y2, y4) - max(y1, y3))
        overlap_area = overlap_x * overlap_y

        # Calculate areas
        area1 = (x2 - x1) * (y2 - y1)
        area2 = (x4 - x3) * (y4 - y3)

        # Check if overlap is significant
        return overlap_area > 0.5 * min(area1, area2)

    # Helper methods
    def _extract_block_text(self, block: Dict) -> str:
        """Extract text from a block."""
        text = ""
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text += span.get("text", "") + " "
        return text.strip()

    def _get_region_bbox(self, region: List[List[Dict]]) -> Tuple[float, float, float, float]:
        """Get bounding box for an entire region."""
        if not region:
            return (0, 0, 0, 0)

        all_blocks = [block for row in region for block in row]
        if not all_blocks:
            return (0, 0, 0, 0)

        x1 = min(block['bbox'][0] for block in all_blocks)
        y1 = min(block['bbox'][1] for block in all_blocks)
        x2 = max(block['bbox'][2] for block in all_blocks)
        y2 = max(block['bbox'][3] for block in all_blocks)

        return (x1, y1, x2, y2)

    def _get_text_region_bbox(self, region: List[Dict]) -> Tuple[float, float, float, float]:
        """Get bounding box for a text region."""
        if not region:
            return (0, 0, 0, 0)

        x1 = min(line['bbox'][0] for line in region if line['bbox'])
        y1 = min(line['bbox'][1] for line in region if line['bbox'])
        x2 = max(line['bbox'][2] for line in region if line['bbox'])
        y2 = max(line['bbox'][3] for line in region if line['bbox'])

        return (x1, y1, x2, y2)

    def _get_grid_bbox(self, grid_structure: Dict) -> Tuple[float, float, float, float]:
        """Get bounding box for a grid structure."""
        h_lines = grid_structure.get('horizontal', [])
        v_lines = grid_structure.get('vertical', [])

        if not h_lines or not v_lines:
            return (0, 0, 0, 0)

        x1 = min(line['x_start'] for line in h_lines)
        x2 = max(line['x_end'] for line in h_lines)
        y1 = min(line['y'] for line in h_lines)
        y2 = max(line['y'] for line in h_lines)

        return (x1, y1, x2, y2)
