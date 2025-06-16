"""Advanced table extraction functionality for PDF processing."""

import re
import fitz
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from ..base import BaseExtractor


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

        # Normalize table data and handle varying column counts
        max_cols = max(len(row) for row in table_data) if table_data else 0
        if max_cols == 0:
            return ""

        # Smart column count detection for academic papers
        # Sometimes the first row is a caption/title, not actual table headers
        actual_table_start = 0
        for i, row in enumerate(table_data):
            if len(row) >= max_cols * 0.7:  # Row has most of the expected columns
                actual_table_start = i
                break

        # Use the detected table start
        working_data = table_data[actual_table_start:]
        if not working_data:
            working_data = table_data

        # Recalculate max columns based on actual table data
        max_cols = max(len(row) for row in working_data) if working_data else 0
        if max_cols < 2:  # Need at least 2 columns for a table
            max_cols = 2

        normalized_data = []
        for row in working_data:
            normalized_row = list(row)
            while len(normalized_row) < max_cols:
                normalized_row.append("")
            # Truncate if too many columns
            normalized_data.append(normalized_row[:max_cols])

        if not normalized_data:
            return ""

        # Create header row - check if first row looks like headers using algorithmic detection
        header = normalized_data[0] if normalized_data else []

        # Use algorithmic patterns instead of hardcoded keywords
        first_row_text = ' '.join(header).lower()
        header_patterns = [
            r'\b[a-z]{4,12}\b',  # Medium-length descriptive words
            # Method/data patterns
            r'\b\w*dat\w*\b|\b\w*model\w*\b|\b\w*method\w*\b|\b\w*approach\w*\b',
            # Performance-related suffixes
            r'\b\w+(?:ness|ity|ance|ence|acy|ion)\b',
            r'\b[A-Z]{2,}\s+\d{4}\b',  # Dataset patterns like "ISIC 2017"
            r'\b\w+[-_]\w+\b',  # Hyphenated or underscore terms
        ]

        has_header_patterns = any(
            re.search(pattern, first_row_text) for pattern in header_patterns)

        if not any(h.strip() for h in header) or not has_header_patterns:
            # Generate descriptive column headers based on content
            header = self._generate_smart_headers(normalized_data, max_cols)
            data_rows = normalized_data
        else:
            data_rows = normalized_data[1:]

        # Clean header cells
        clean_header = []
        for i, cell in enumerate(header):
            cleaned = re.sub(r'[|\n\r]', ' ', str(cell)).strip()
            if not cleaned:
                cleaned = f"Column {i+1}"
            # Capitalize first letter for better formatting
            cleaned = cleaned[0].upper() + \
                cleaned[1:] if cleaned else f"Column {i+1}"
            clean_header.append(cleaned)

        # Build markdown table
        markdown_lines.append("| " + " | ".join(clean_header) + " |")

        # Create separator row with appropriate alignment
        separators = []
        for i, header_cell in enumerate(clean_header):
            # Check if this column contains mostly numbers (right-align)
            column_values = [row[i] if i < len(
                row) else "" for row in data_rows]
            column_text = ' '.join(column_values)

            if self.detect_numerical_patterns(column_text):
                separators.append("---:")  # Right align for numbers
            else:
                separators.append("---")   # Left align for text

        markdown_lines.append("| " + " | ".join(separators) + " |")

        # Add data rows with enhanced formatting
        for row in data_rows:
            clean_row = []
            for i, cell in enumerate(row):
                # Clean cell content
                cleaned = re.sub(r'[|\n\r]', ' ', str(cell)).strip()
                # Escape any remaining pipes
                cleaned = cleaned.replace('|', '\\|')

                # Format numerical values better
                if re.search(r'^\d+\.\d+$', cleaned):
                    try:
                        # Format to reasonable decimal places
                        num_val = float(cleaned)
                        if num_val < 1:
                            cleaned = f"{num_val:.3f}"
                        else:
                            cleaned = f"{num_val:.2f}"
                    except ValueError:
                        pass

                clean_row.append(cleaned)

            markdown_lines.append("| " + " | ".join(clean_row) + " |")

        markdown_lines.append("")  # Add spacing after table

        return "\n".join(markdown_lines)

    def _generate_smart_headers(self, table_data: List[List[str]], max_cols: int) -> List[str]:
        """Generate smart column headers based on table content."""
        headers = []

        # Analyze each column to determine appropriate header
        for col_idx in range(max_cols):
            column_values = []
            for row in table_data:
                if col_idx < len(row) and row[col_idx].strip():
                    column_values.append(row[col_idx].strip())

            if not column_values:
                headers.append(f"Column {col_idx + 1}")
                continue

            # Analyze column content to suggest header
            column_text = ' '.join(column_values).lower()

            # Check for common academic paper patterns using algorithmic detection
            if col_idx == 0:
                if any(re.search(r'\(.*\d{4}.*\)', val) for val in column_values):
                    headers.append("Reference")
                elif any(re.search(r'\b[A-Za-z]+(?:[-_][A-ZaZ]+)*\b', val) for val in column_values):
                    headers.append("Method")
                else:
                    headers.append("Approach")
            elif self.detect_numerical_patterns(column_text):
                # Numerical column - determine type using algorithmic patterns
                if re.search(r'\d+\.?\d*%|\b\w*acc\w*\b|\b\w*prec\w*\b', column_text):
                    headers.append("Accuracy")
                elif re.search(r'\b\w*loss\w*\b|\b\w*err\w*\b', column_text):
                    headers.append("Loss")
                elif re.search(r'\b\w*time\w*\b|\b\w*speed\w*\b|\bms\b|\bs\b', column_text):
                    headers.append("Time")
                else:
                    headers.append("Metric")
            else:
                # Text column using algorithmic patterns
                if re.search(r'\b\w*dat\w*\b|\b\w*corp\w*\b|\b\w*bench\w*\b', column_text):
                    headers.append("Dataset")
                elif re.search(r'\b\w*arch\w*\b|\b\w*net\w*\b|\b\w*model\w*\b', column_text):
                    headers.append("Architecture")
                elif re.search(r'\b\w*type\w*\b|\b\w*class\w*\b|\b\w*categ\w*\b', column_text):
                    headers.append("Type")
                else:
                    headers.append(f"Column {col_idx + 1}")

        return headers

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

    def extract_tables_from_text(self, text: str, page_num: int = 0) -> List[Dict[str, Any]]:
        """Extract tables from plain text with improved academic paper handling."""
        tables = []

        # Split text into lines
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        # Find all table sections with their complete content
        table_sections = self._find_complete_table_sections(lines)

        # Consolidate related table sections that should be one table
        consolidated_sections = self._consolidate_related_table_sections(
            table_sections)

        for section_idx, section in enumerate(consolidated_sections):
            table_data = self._parse_academic_table_section(section)
            if table_data and self._validate_academic_table(table_data):
                confidence = self._calculate_academic_table_confidence(
                    table_data)

                tables.append({
                    'type': 'academic_text_table',
                    'page': page_num,
                    'region_id': section_idx,
                    'data': table_data,
                    'confidence': confidence,
                    'bbox': (0, 0, 0, 0),
                    'title': section.get('title', ''),
                    'description': section.get('description', '')
                })

        return tables

    def _detect_table_title(self, line_lower: str, original_line: str) -> re.Match:
        """Robust table title detection with multiple patterns."""
        # Multiple table title patterns to try (in order of preference)
        patterns = [
            # Standard formats
            # Table 1. Title
            r'table\s+(\d+)\.?\s*(.*)',
            # Table 1 - Title or Table 1: Title
            r'table\s+(\d+)\s*[-:]\s*(.*)',
            # Table 1 . Title
            r'table\s+(\d+)\s*\.\s*(.*)',
            # Table 1 Title (no punctuation)
            r'table\s+(\d+)\s+(.*)',

            # Roman numerals
            # Table I. Title
            r'table\s+([ivxlc]+)\.?\s*(.*)',
            # Table I - Title
            r'table\s+([ivxlc]+)\s*[-:]\s*(.*)',

            # Letter designations
            # Table A. Title
            r'table\s+([a-z])\.?\s*(.*)',
            # Table A - Title
            r'table\s+([a-z])\s*[-:]\s*(.*)',

            # Alternative formats
            # Table1. Title (no space)
            r'table\s*(\d+)\.?\s*(.*)',
            # Tab. 1. Title
            r'tab\.\s*(\d+)\.?\s*(.*)',
            # Tbl. 1. Title
            r'tbl\.?\s*(\d+)\.?\s*(.*)',

            # Multi-word variations
            # Table 1. Multi-sentence title.
            r'table\s+(\d+)\.\s*([^.]+\..*)',
            # Table 1 – Title (various dashes)
            r'table\s+(\d+)\s*[\-–—]\s*(.*)',

            # Parenthetical numbering
            # Table (1) Title
            r'table\s*\((\d+)\)\s*(.*)',
            # Table [1] Title
            r'table\s*\[(\d+)\]\s*(.*)',

            # No number (fallback)
            # Table - Title or Table: Title
            r'table\s*[-:]\s*(.*)',
            # Table Title (last resort)
            r'table\s+(.*)',
        ]

        for pattern in patterns:
            match = re.search(pattern, line_lower, re.IGNORECASE)
            if match:
                # For patterns without explicit number capture, assign a default
                if len(match.groups()) == 1:
                    # Create a mock match object with number and description
                    class MockMatch:
                        def __init__(self, groups):
                            self.groups_list = groups

                        def group(self, n):
                            return self.groups_list[n-1] if n <= len(self.groups_list) else ''

                        def groups(self):
                            return tuple(self.groups_list)

                    # If only description captured, assign number as '1'
                    return MockMatch(['1', match.group(1)])
                else:
                    return match

        # Additional check for lines that might be table headers without explicit "Table" word
        # but have table-like structure
        if self._looks_like_table_header_line(original_line):
            class MockMatch:
                def __init__(self, groups):
                    self.groups_list = groups

                def group(self, n):
                    return self.groups_list[n-1] if n <= len(self.groups_list) else ''

                def groups(self):
                    return tuple(self.groups_list)

            return MockMatch(['1', original_line.strip()])

        return None

    def _looks_like_table_header_line(self, line: str) -> bool:
        """Check if a line looks like a table header even without 'Table' word."""
        # Look for common table header patterns using algorithmic detection
        header_indicators = [
            # Performance metrics (algorithmic pattern for metric-like terms)
            # Performance-related suffixes
            r'\b\w+(?:ness|ity|ance|ence|acy|ion)\b',
            # Method/approach terms (algorithmic pattern)
            # Hyphenated or underscore technical terms
            r'\b[A-Za-z]+(?:[-_][A-Za-z]+)*\b',
            # Data-related terms (algorithmic pattern)
            r'\b\w*dat\w*\b|\b\w*corp\w*\b|\b\w*bench\w*\b',  # Data/corpus/benchmark patterns
            # Result/metric terms (algorithmic pattern)
            r'\b\w*result\w*\b|\b\w*perform\w*\b|\b\w*score\w*\b|\b\w*metric\w*\b',  # Result patterns
            # Parameter terms (algorithmic pattern)
            r'\b\w*param\w*\b|\b\w*flop\w*\b',  # Parameter patterns
            # Multiple capital letters (likely abbreviations)
            r'\b[A-Z]{2,}\b.*\b[A-Z]{2,}\b',
            # Numeric patterns suggesting column headers
            r'\d+\s+\d+\s+\d+',
        ]

        line_lower = line.lower()
        indicator_count = sum(1 for pattern in header_indicators
                              if re.search(pattern, line_lower, re.IGNORECASE))

        # Must have at least 2 indicators and reasonable length
        return indicator_count >= 2 and 10 <= len(line) <= 200

    def _find_complete_table_sections(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Find complete table sections including titles, headers, and data with enhanced detection."""
        sections = []
        current_section = None

        i = 0
        while i < len(lines):
            line = lines[i]
            line_lower = line.lower()

            # Check for table title patterns with multiple robust patterns
            table_title_match = self._detect_table_title(line_lower, line)

            if table_title_match:
                # Save previous section
                if current_section and len(current_section.get('content_lines', [])) >= 2:
                    sections.append(current_section)

                # Start new section
                current_section = {
                    'title': line,
                    'table_number': table_title_match.group(1),
                    'description': table_title_match.group(2).strip(),
                    'content_lines': [],
                    'start_line': i
                }
                i += 1
                continue

            # If we're in a table section, collect content
            if current_section is not None:
                # Check if this line looks like table content
                if self._looks_like_table_content(line, current_section['content_lines']):
                    current_section['content_lines'].append(line)
                else:
                    # End current table section if we hit non-table content
                    if len(current_section.get('content_lines', [])) >= 2:
                        sections.append(current_section)
                    current_section = None

            i += 1

        # Handle section at end
        if current_section and len(current_section.get('content_lines', [])) >= 2:
            sections.append(current_section)

        # Fallback: If no sections found with explicit table titles,
        # look for table-like content blocks
        if not sections:
            sections = self._find_implicit_table_sections(lines)

        return sections

    def _find_implicit_table_sections(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Find table sections without explicit 'Table' titles."""
        sections = []
        potential_tables = []
        current_block = []

        for i, line in enumerate(lines):
            if self._looks_like_table_row(line):
                current_block.append(line)
            else:
                if len(current_block) >= 3:  # At least header + 2 data rows
                    potential_tables.append({
                        'start_line': i - len(current_block),
                        'content_lines': current_block.copy(),
                        'title': f'Table (detected at line {i - len(current_block) + 1})',
                        'table_number': '1',
                        'description': 'Implicitly detected table'
                    })
                current_block = []

        # Handle final block
        if len(current_block) >= 3:
            potential_tables.append({
                'start_line': len(lines) - len(current_block),
                'content_lines': current_block.copy(),
                'title': f'Table (detected at line {len(lines) - len(current_block) + 1})',
                'table_number': '1',
                'description': 'Implicitly detected table'
            })

        return potential_tables

    def _looks_like_table_row(self, line: str) -> bool:
        """Check if a line looks like a table row."""
        if not line.strip() or len(line.strip()) < 5:
            return False

        # Check for table row indicators
        indicators = {
            'has_multiple_numbers': len(re.findall(r'\d+\.?\d*', line)) >= 2,
            'has_method_name': bool(re.search(r'^[A-Za-z][\w\-]+', line.strip())),
            'has_citations': bool(re.search(r'\[.*?\]|\(\d{4}\)', line)),
            'has_percentages': bool(re.search(r'\d+\.?\d*%', line)),
            'word_count_reasonable': 3 <= len(line.split()) <= 20,
            'has_mixed_content': bool(re.search(r'[A-Za-z].*\d+|\d+.*[A-Za-z]', line))
        }

        # A line is likely a table row if it has multiple indicators
        indicator_count = sum(indicators.values())
        return indicator_count >= 2

    def _looks_like_table_content(self, line: str, existing_lines: List[str]) -> bool:
        """Determine if a line looks like table content using algorithmic detection."""
        if not line.strip():
            return False

        # Check for various table content indicators
        features = {
            'has_numbers': bool(re.search(r'\d+\.?\d*%?', line)),
            'has_parentheses': '(' in line and ')' in line,
            'has_commas': ',' in line,
            'word_count': len(line.split()),
            'has_abbreviations': bool(re.search(r'\b[A-Z]{2,}\b', line)),
            'has_citations': bool(re.search(r'\bet al\.|\(\d{4}\)', line)),
            'has_structured_data': bool(re.search(r'\d+\.?\d*[%]?|\([^)]*\d+[^)]*\)', line)),
            'line_length': len(line)
        }

        # If this is the first content line, be permissive
        if not existing_lines:
            return features['word_count'] >= 2

        # Academic table content patterns - be more permissive
        academic_content_indicators = [
            features['has_numbers'],
            features['has_abbreviations'],
            features['has_citations'],
            features['has_structured_data'],
            # Repeated patterns (like "DSC SE SP ACC DSC SE SP ACC")
            len(set(line.split())) < len(
                line.split()) * 0.7,  # 70% unique words
            # Technical terms and acronyms common in academic tables
            # Acronyms like DSC, SE, SP, ACC
            bool(re.search(r'\b[A-Z]{2,4}\b', line)),
            # Method names and citations
            # Hyphenated terms
            bool(re.search(r'\b[A-Za-z]+-[A-Za-z]+\b', line)),
            # Metric-like patterns (algorithmic detection)
            # Sequences of short lowercase words (metrics)
            bool(
                re.search(r'\b[a-z]{2,6}\b(?:\s+[a-z]{2,6}\b){1,4}', line.lower())),
            # Performance-related patterns (without hardcoding specific terms)
            # Performance-related suffixes
            bool(re.search(r'\b\w+(?:ness|ity|ance|ence|acy|ion)\b', line.lower())),
            # Mathematical/statistical indicators
            # Variables with numbers (F1, R2, etc.)
            bool(re.search(r'\b[a-z]\d+\b|\b\w+[-_]?\d+\b', line.lower())),
        ]

        # If it has multiple academic indicators, accept it
        if sum(academic_content_indicators) >= 2:
            return True

        # Calculate similarity with existing table lines
        if existing_lines:
            avg_word_count = sum(len(l.split())
                                 for l in existing_lines) / len(existing_lines)
            word_count_similarity = abs(
                features['word_count'] - avg_word_count) <= 6  # More tolerant

            has_similar_patterns = any([
                features['has_numbers'] and any(
                    re.search(r'\d+\.?\d*%?', l) for l in existing_lines),
                features['has_parentheses'] and any(
                    '(' in l for l in existing_lines),
                features['has_citations'] and any(
                    re.search(r'\bet al\.|\(\d{4}\)', l) for l in existing_lines),
                features['has_structured_data'] and any(
                    re.search(r'\d+\.?\d*[%]?|\([^)]*\d+[^)]*\)', l) for l in existing_lines),
                # Similar abbreviation patterns
                features['has_abbreviations'] and any(
                    re.search(r'\b[A-Z]{2,4}\b', l) for l in existing_lines)
            ])

            return word_count_similarity or has_similar_patterns

        return True

    def _parse_academic_table_section(self, section: Dict[str, Any]) -> Optional[List[List[str]]]:
        """Parse an academic table section into structured data."""
        content_lines = section.get('content_lines', [])
        if not content_lines:
            return None

        # Analyze the entire table structure first to determine optimal column layout
        column_structure = self._analyze_table_column_structure(content_lines)
        if not column_structure:
            return None

        # Identify header row and data rows
        header_row = None
        data_rows = []

        # Look for header patterns in first few lines
        for i, line in enumerate(content_lines[:3]):
            if self._looks_like_header_row(line):
                header_row = line
                data_rows = content_lines[i+1:]
                break

        # If no clear header found, use first line as header
        if header_row is None:
            header_row = content_lines[0]
            data_rows = content_lines[1:]

        # Parse header into columns using discovered structure
        header_columns = self._parse_table_row_with_structure(
            header_row, column_structure)
        if not header_columns:
            return None

        # Parse data rows using the same structure
        table_data = [header_columns]
        for row_line in data_rows:
            row_data = self._parse_table_row_with_structure(
                row_line, column_structure)
            if row_data:
                table_data.append(row_data)

        return table_data if len(table_data) >= 2 else None

    def _analyze_table_column_structure(self, lines: List[str]) -> Optional[Dict[str, Any]]:
        """Analyze all table lines to determine optimal column structure with improved prioritization."""
        if not lines:
            return None

        # Remove empty lines and very short lines
        non_empty_lines = [
            line for line in lines if line.strip() and len(line.strip()) > 5]
        if len(non_empty_lines) < 2:
            return None

        # Score different strategies and pick the best one
        strategies = []

        # Strategy 0: Academic citation + numerical data pattern (highest priority)
        # For this strategy, only use lines that have citation patterns (])
        # since headers typically don't have citations
        data_rows = [line for line in non_empty_lines if ']' in line]
        if data_rows:  # Only try if we have potential data rows with citations
            academic_structure = self._find_academic_citation_numerical_structure(
                data_rows)
            if academic_structure:
                score = 10  # Highest priority for academic tables
                strategies.append({
                    'score': score,
                    'structure': {
                        'type': 'academic_citation_numerical',
                        'citation_end_patterns': academic_structure['citation_end_patterns'],
                        'numerical_groups': academic_structure['numerical_groups'],
                        'column_count': academic_structure['column_count']
                    }
                })

        # Strategy 1: Multi-space separators (high priority if found)
        multi_space_structure = self._find_multi_space_columns(non_empty_lines)
        if multi_space_structure:
            # Score based on number of consistent positions and column count reasonableness
            score = len(multi_space_structure['positions']) * 2
            # Allow up to 15 columns for academic tables
            if 2 <= multi_space_structure['column_count'] <= 15:
                score += 5  # Bonus for reasonable column count
            strategies.append({
                'score': score,
                'structure': {
                    'type': 'multi_space',
                    'positions': multi_space_structure['positions'],
                    'column_count': multi_space_structure['column_count']
                }
            })

        # Strategy 2: Positional analysis (good for well-aligned tables)
        positional_structure = self._find_positional_columns(non_empty_lines)
        if positional_structure:
            score = len(positional_structure['positions'])
            # Allow up to 15 columns
            if 2 <= positional_structure['column_count'] <= 15:
                score += 3
            strategies.append({
                'score': score,
                'structure': {
                    'type': 'positional',
                    'positions': positional_structure['positions'],
                    'column_count': positional_structure['column_count']
                }
            })

        # Strategy 3: Tab separators (reliable but less common)
        tab_structure = self._find_tab_columns(non_empty_lines)
        if tab_structure:
            score = 4  # Fixed moderate score
            if 2 <= tab_structure['column_count'] <= 15:  # Allow up to 15 columns
                score += 2
            strategies.append({
                'score': score,
                'structure': {
                    'type': 'tab',
                    'column_count': tab_structure['column_count']
                }
            })

        # Strategy 4: Pattern-based (good for content with clear patterns)
        pattern_structure = self._find_pattern_based_columns(non_empty_lines)
        if pattern_structure:
            score = len(pattern_structure['patterns'])
            # Allow up to 15 columns
            if 2 <= pattern_structure['column_count'] <= 15:
                score += 1
            strategies.append({
                'score': score,
                'structure': {
                    'type': 'pattern',
                    'patterns': pattern_structure['patterns'],
                    'column_count': pattern_structure['column_count']
                }
            })

        # Choose the highest scoring strategy
        if strategies:
            best_strategy = max(strategies, key=lambda x: x['score'])
            return best_strategy['structure']

        # Fallback: Intelligent word-based splitting
        estimated_columns = self._estimate_column_count_from_words(
            non_empty_lines)
        return {
            'type': 'word_based',
            'column_count': estimated_columns
        }

    def _find_multi_space_columns(self, lines: List[str]) -> Optional[Dict[str, Any]]:
        """Find consistent multi-space column separators across lines with improved accuracy."""
        if not lines:
            return None

        # First, find all potential separator positions (2+ spaces)
        all_gap_positions = []

        for line in lines:
            if not line.strip():
                continue

            # Find positions of 2+ consecutive spaces
            gap_positions = []
            for match in re.finditer(r'\s{2,}', line):
                start_pos = match.start()
                end_pos = match.end()
                # Use the middle of the gap as the separator position
                gap_positions.append((start_pos + end_pos) // 2)
            all_gap_positions.append(gap_positions)

        if not all_gap_positions:
            return None

        # Create position clusters with tolerance
        position_clusters = []
        tolerance = 4  # Characters tolerance for grouping positions

        for positions in all_gap_positions:
            for pos in positions:
                # Find existing cluster this position belongs to
                added_to_cluster = False
                for cluster in position_clusters:
                    if any(abs(pos - existing_pos) <= tolerance for existing_pos in cluster):
                        cluster.append(pos)
                        added_to_cluster = True
                        break

                # Create new cluster if no match found
                if not added_to_cluster:
                    position_clusters.append([pos])

        # Filter clusters that appear in enough lines (at least 50%)
        min_frequency = max(1, len(lines) * 0.5)
        valid_clusters = [cluster for cluster in position_clusters
                          if len(cluster) >= min_frequency]

        if not valid_clusters:
            return None

        # Get representative position for each cluster (median)
        separator_positions = []
        for cluster in valid_clusters:
            cluster.sort()
            median_pos = cluster[len(cluster) // 2]
            separator_positions.append(median_pos)

        separator_positions.sort()

        # Ensure minimum distance between separators
        min_distance = 8  # Minimum characters between columns
        filtered_positions = []
        for i, pos in enumerate(separator_positions):
            if i == 0 or pos - filtered_positions[-1] >= min_distance:
                filtered_positions.append(pos)

        if len(filtered_positions) >= 1:
            return {
                'positions': filtered_positions,
                'column_count': len(filtered_positions) + 1
            }

        return None

    def _find_tab_columns(self, lines: List[str]) -> Optional[Dict[str, Any]]:
        """Find consistent tab-separated columns."""
        tab_counts = [line.count('\t') for line in lines]
        if not tab_counts or max(tab_counts) == 0:
            return None

        # Check if most lines have similar tab counts
        most_common_count = max(set(tab_counts), key=tab_counts.count)
        consistent_lines = sum(
            1 for count in tab_counts if count == most_common_count)

        if consistent_lines >= len(lines) * 0.7:  # 70% consistency
            return {'column_count': most_common_count + 1}

        return None

    def _find_pattern_based_columns(self, lines: List[str]) -> Optional[Dict[str, Any]]:
        """Find columns based on content patterns."""
        patterns = []

        # Look for common academic table patterns using algorithmic detection
        academic_patterns = [
            (r'^[A-Za-z][^0-9]*?\bet al\.',
             'author_reference'),  # Author citations
            # Years in parentheses
            (r'\([^)]*\d{4}[^)]*\)', 'year_parentheses'),
            # Dataset references (algorithmic)
            (r'\([^)]*(?:dataset|data|corpus|benchmark)[^)]*\)',
             'dataset_parentheses'),
            (r'\d+\.?\d*%', 'percentage'),                         # Percentages
            # Numbers with common units (algorithmic)
            (r'\d+\.?\d*[MKBGTmkμnpf]?[BWHzsFLVA]?\b', 'numbers_with_units'),
            # Scientific notation
            (r'\d+\.?\d*[eE][+-]?\d+', 'scientific_notation'),
            # Capitalized technical terms (likely model/method names)
            (r'\b[A-Z][a-zA-Z]*(?:[A-Z][a-zA-Z]*){1,3}\b', 'technical_terms'),
            # Acronyms and abbreviations
            (r'\b[A-Z]{2,6}\b(?:-\d+)?', 'acronyms'),
            # Version numbers or model variants
            (r'\b[A-Za-z]+[-_]?\d+(?:\.\d+)*\b', 'versioned_terms'),
            # Hyphenated technical terms
            (r'\b[A-Za-z]+(?:-[A-Za-z]+){1,3}\b', 'hyphenated_terms'),
        ]

        # Analyze which patterns appear in which positions across lines
        pattern_positions = {pattern_name: []
                             for _, pattern_name in academic_patterns}

        for line in lines:
            line_patterns = {}
            for pattern, pattern_name in academic_patterns:
                matches = list(re.finditer(pattern, line, re.IGNORECASE))
                if matches:
                    # Record the position of the first match
                    line_patterns[pattern_name] = matches[0].start()

            for pattern_name, pos in line_patterns.items():
                pattern_positions[pattern_name].append(pos)

        # Find patterns that appear consistently in similar positions
        consistent_patterns = []
        for pattern_name, positions in pattern_positions.items():
            if len(positions) >= max(2, len(lines) * 0.5):  # Appears in at least half the lines
                avg_pos = sum(positions) / len(positions)
                consistent_patterns.append({
                    'name': pattern_name,
                    'avg_position': avg_pos,
                    'frequency': len(positions)
                })

        if consistent_patterns:
            # Sort by position to determine column order
            consistent_patterns.sort(key=lambda x: x['avg_position'])
            return {
                'patterns': consistent_patterns,
                'column_count': len(consistent_patterns) + 1
            }

        return None

    def _find_positional_columns(self, lines: List[str]) -> Optional[Dict[str, Any]]:
        """Find column boundaries based on improved character position analysis."""
        if not lines:
            return None

        # Filter out empty lines
        non_empty_lines = [line for line in lines if line.strip()]
        if not non_empty_lines:
            return None

        max_length = max(len(line) for line in non_empty_lines)
        if max_length < 10:  # Too short to have meaningful columns
            return None

        # Analyze character and whitespace distribution
        char_density = [0] * max_length
        space_density = [0] * max_length

        for line in non_empty_lines:
            for i, char in enumerate(line):
                if char.strip():  # Non-whitespace character
                    char_density[i] += 1
                else:  # Whitespace
                    space_density[i] += 1

        # Find potential column separator regions (high whitespace, low content)
        total_lines = len(non_empty_lines)
        separator_candidates = []

        for i in range(5, max_length - 5):  # Skip edges
            # High whitespace density and low character density indicates separator
            space_ratio = space_density[i] / total_lines
            char_ratio = char_density[i] / total_lines

            if space_ratio >= 0.6 and char_ratio <= 0.3:
                # Check for consistent gaps in surrounding area
                local_space_avg = sum(space_density[max(0, i-3):i+4]) / 7
                if local_space_avg >= total_lines * 0.5:
                    separator_candidates.append(i)

        if not separator_candidates:
            return None

        # Group nearby candidates into regions
        separator_regions = []
        current_region = [separator_candidates[0]]

        for candidate in separator_candidates[1:]:
            if candidate - current_region[-1] <= 3:  # Nearby positions
                current_region.append(candidate)
            else:
                # End current region, start new one
                separator_regions.append(current_region)
                current_region = [candidate]

        if current_region:
            separator_regions.append(current_region)

        # Take the center of each region as the separator position
        separator_positions = []
        min_distance = 8  # Minimum distance between separators

        for region in separator_regions:
            center_pos = region[len(region) // 2]
            # Ensure minimum distance from previous separators
            if not separator_positions or center_pos - separator_positions[-1] >= min_distance:
                separator_positions.append(center_pos)

        if len(separator_positions) >= 1:
            return {
                'positions': separator_positions,
                'column_count': len(separator_positions) + 1
            }

        return None

    def _find_academic_citation_numerical_structure(self, lines: List[str]) -> Optional[Dict[str, Any]]:
        """Detect academic table pattern: method name with citation + groups of numerical data."""
        if not lines:
            return None

        citation_patterns = []
        numerical_groups = []

        for line in lines:
            words = line.split()
            if len(words) < 5:  # Need at least method + some numbers
                continue

            # Look for citation end patterns: ] followed by numbers
            citation_end_idx = None
            for i, word in enumerate(words):
                # At least 4 more words after ]
                if word == ']' and i < len(words) - 4:
                    # Check if remaining words are mostly numerical
                    remaining_words = words[i+1:]
                    numerical_count = sum(1 for w in remaining_words
                                          if self._is_numerical_value(w))

                    if numerical_count >= len(remaining_words) * 0.8:  # 80% numerical
                        citation_end_idx = i
                        break

            if citation_end_idx is not None:
                citation_patterns.append(citation_end_idx)
                remaining_numbers = words[citation_end_idx + 1:]

                # Try to group numbers into columns (common academic pattern: groups of 3-5)
                if len(remaining_numbers) >= 8:  # At least 8 numbers for meaningful grouping
                    if len(remaining_numbers) % 4 == 0:
                        group_size = 4
                    elif len(remaining_numbers) % 3 == 0:
                        group_size = 3
                    elif len(remaining_numbers) % 5 == 0:
                        group_size = 5
                    else:
                        # Default grouping
                        group_size = len(remaining_numbers) // 3

                    num_groups = len(remaining_numbers) // group_size
                    numerical_groups.append({
                        'total_numbers': len(remaining_numbers),
                        'group_size': group_size,
                        'num_groups': num_groups
                    })

        # Check if we found consistent patterns
        if len(citation_patterns) >= 2:  # At least 2 lines with this pattern
            # Check for consistency in citation end positions (within tolerance)
            avg_citation_pos = sum(citation_patterns) / len(citation_patterns)
            consistent_citations = sum(1 for pos in citation_patterns
                                       if abs(pos - avg_citation_pos) <= 1)

            # 70% consistency
            if consistent_citations >= len(citation_patterns) * 0.7:
                # Check for consistency in numerical grouping
                if numerical_groups:
                    most_common_groups = max(set(g['num_groups'] for g in numerical_groups),
                                             key=lambda x: sum(1 for g in numerical_groups if g['num_groups'] == x))

                    return {
                        'citation_end_patterns': citation_patterns,
                        'numerical_groups': numerical_groups,
                        'column_count': most_common_groups + 1,  # +1 for method column
                        'avg_citation_pos': avg_citation_pos
                    }

        return None

    def _is_numerical_value(self, word: str) -> bool:
        """Check if a word represents a numerical value (including percentages, decimals, etc.)."""
        # Remove common numerical formatting
        cleaned = word.strip('[]()%,')

        # Check various numerical patterns
        patterns = [
            r'^\d+$',                    # Integer
            r'^\d+\.\d+$',              # Decimal
            r'^\d+\.\d+%$',             # Percentage
            r'^\d+[eE][+-]?\d+$',       # Scientific notation
            r'^\d+\.\d+[eE][+-]?\d+$',  # Decimal scientific notation
        ]

        for pattern in patterns:
            if re.match(pattern, cleaned):
                return True

        return False

    def _parse_table_row_with_structure(self, line: str, structure: Dict[str, Any]) -> List[str]:
        """Parse a table row using the determined column structure."""
        if not line.strip():
            return []

        structure_type = structure.get('type', 'word_based')

        if structure_type == 'academic_citation_numerical':
            return self._split_academic_citation_numerical(line, structure)
        elif structure_type == 'multi_space':
            return self._split_by_positions(line, structure['positions'])
        elif structure_type == 'tab':
            columns = line.split('\t')
            return [col.strip() for col in columns if col.strip()]
        elif structure_type == 'pattern':
            return self._split_by_patterns(line, structure['patterns'])
        elif structure_type == 'positional':
            return self._split_by_positions(line, structure['positions'])
        else:  # word_based
            return self._split_by_word_groups(line, structure['column_count'])

    def _split_academic_citation_numerical(self, line: str, structure: Dict[str, Any]) -> List[str]:
        """Split line based on academic citation + numerical pattern."""
        words = line.split()
        if not words:
            return []

        # Find the citation end (])
        citation_end_idx = None
        for i, word in enumerate(words):
            if word == ']' and i < len(words) - 1:
                citation_end_idx = i
                break

        if citation_end_idx is not None:
            # Method name is everything up to and including ]
            method_name = ' '.join(words[:citation_end_idx + 1])
            remaining_numbers = words[citation_end_idx + 1:]

            # Group the remaining numbers based on the detected pattern
            numerical_groups = structure.get('numerical_groups', [])
            if numerical_groups:
                # Use the most common grouping pattern
                group_sizes = [g['group_size'] for g in numerical_groups]
                most_common_size = max(
                    set(group_sizes), key=group_sizes.count) if group_sizes else 4

                columns = [method_name]

                # Group numbers by the detected size
                for i in range(0, len(remaining_numbers), most_common_size):
                    group = remaining_numbers[i:i + most_common_size]
                    if group:  # Only add non-empty groups
                        columns.append(' '.join(group))

                return columns
            else:
                # Fallback: assume groups of 4 (common in academic tables)
                columns = [method_name]
                group_size = 4

                for i in range(0, len(remaining_numbers), group_size):
                    group = remaining_numbers[i:i + group_size]
                    if group:
                        columns.append(' '.join(group))

                return columns
        else:
            # No citation pattern found, fall back to word-based splitting
            return self._split_by_word_groups(line, structure.get('column_count', 4))

    def _deduplicate_and_filter_tables(self, tables: List[Dict]) -> List[Dict]:
        """Remove duplicate tables and filter by confidence."""
        return [t for t in tables if t['confidence'] >= self.min_table_confidence]

    def _get_region_bbox(self, region: List[List[Dict]]) -> Tuple[float, float, float, float]:
        """Get bounding box for an entire region."""
        return (0, 0, 0, 0)  # Simplified for modularity

    def _get_text_region_bbox(self, region: List[Dict]) -> Tuple[float, float, float, float]:
        """Get bounding box for a text region."""
        return (0, 0, 0, 0)  # Simplified for modularity

    def _get_grid_bbox(self, grid_structure: Dict) -> Tuple[float, float, float, float]:
        """Get bounding box for a grid structure."""
        return (0, 0, 0, 0)  # Simplified for modularity

    def _consolidate_related_table_sections(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Consolidate table sections that should be one unified table."""
        if not sections:
            return []

        consolidated = []
        current_group = None

        for section in sections:
            title = section.get('title', '').lower()
            content_lines = section.get('content_lines', [])

            # Check if this section should be merged with the previous one
            should_merge = False

            if current_group is not None:
                # Merge if:
                # 1. No explicit table title (continuation of previous table)
                # 2. Similar table number or continuation pattern
                # 3. Content structure suggests it's part of the same table

                current_title = current_group.get('title', '').lower()

                # Check for continuation patterns
                if (not re.search(r'table\s+\d+', title) or  # No new table number
                    self._similar_table_structure(current_group['content_lines'], content_lines) or
                        self._likely_table_continuation(current_group['content_lines'], content_lines)):
                    should_merge = True

            if should_merge:
                # Merge with current group
                current_group['content_lines'].extend(content_lines)
                if not current_group.get('description') and section.get('description'):
                    current_group['description'] = section['description']
            else:
                # Start new group
                if current_group:
                    consolidated.append(current_group)
                current_group = section.copy()

        # Add final group
        if current_group:
            consolidated.append(current_group)

        return consolidated

    def _similar_table_structure(self, lines1: List[str], lines2: List[str]) -> bool:
        """Check if two sets of lines have similar table structure."""
        if not lines1 or not lines2:
            return False

        # Analyze structure of a few lines from each
        sample1 = lines1[:3]
        sample2 = lines2[:3]

        # Check for similar patterns in word counts and numeric content
        for line1, line2 in zip(sample1, sample2):
            words1 = len(line1.split())
            words2 = len(line2.split())

            nums1 = len(re.findall(r'\d+\.?\d*', line1))
            nums2 = len(re.findall(r'\d+\.?\d*', line2))

            # Similar structure if word counts and numeric patterns are close
            if abs(words1 - words2) <= 3 and abs(nums1 - nums2) <= 2:
                return True

        return False

    def _likely_table_continuation(self, prev_lines: List[str], curr_lines: List[str]) -> bool:
        """Check if current lines are likely continuation of previous table."""
        if not prev_lines or not curr_lines:
            return False

        # Check if the first line of curr_lines looks like a data row
        # rather than a header (which would indicate a new table)
        first_curr_line = curr_lines[0]

        # If it starts with a method name or contains many numbers, likely continuation
        has_method_pattern = bool(
            re.search(r'^[A-Za-z][\w\-]+', first_curr_line))
        has_many_numbers = len(re.findall(r'\d+\.?\d*', first_curr_line)) >= 3

        # Check if it doesn't look like a header using algorithmic patterns
        header_patterns = [
            r'\b\w*method\w*\b|\b\w*approach\w*\b',  # Method patterns
            r'\b\w*model\w*\b|\b\w*dat\w*\b',  # Model/data patterns
            r'\b\w*param\w*\b|\b\w*flop\w*\b',  # Parameter patterns
        ]
        looks_like_header = any(re.search(pattern, first_curr_line.lower())
                                for pattern in header_patterns)

        return (has_method_pattern or has_many_numbers) and not looks_like_header

    def _calculate_academic_table_confidence(self, table_data: List[List[str]]) -> float:
        """Calculate confidence score for academic table."""
        if not table_data:
            return 0.0

        confidence_factors = []

        # Factor 1: Table size and completeness
        total_cells = sum(len(row) for row in table_data)
        non_empty_cells = sum(
            1 for row in table_data for cell in row if cell.strip())
        completeness = non_empty_cells / total_cells if total_cells > 0 else 0
        confidence_factors.append(completeness)

        # Factor 2: Consistent row lengths
        row_lengths = [len(row) for row in table_data]
        if row_lengths:
            max_len = max(row_lengths)
            min_len = min(row_lengths)
            consistency = min_len / max_len if max_len > 0 else 0
            confidence_factors.append(consistency)

        # Factor 3: Presence of numeric data (common in academic tables)
        numeric_score = 0
        for row in table_data:
            for cell in row:
                if re.search(r'\d+\.?\d*', cell):
                    numeric_score += 1

        numeric_ratio = numeric_score / total_cells if total_cells > 0 else 0
        confidence_factors.append(min(numeric_ratio * 2, 1.0))  # Cap at 1.0

        # Factor 4: Academic content patterns
        academic_score = 0
        all_text = ' '.join(' '.join(row) for row in table_data).lower()

        academic_patterns = [
            r'\bet al\.',
            r'\(\d{4}\)',
            # Performance-related patterns (algorithmic)
            # Performance-related suffixes
            r'\b\w+(?:ness|ity|ance|ence|acy|ion)\b',
            # Method/data-related patterns (algorithmic)
            # Dataset/method patterns
            r'\b\w*dat\w*\b|\b\w*model\w*\b|\b\w*method\w*\b|\b\w*approach\w*\b',
            r'\d+\.?\d*%',
            r'\b[A-Z]{2,}\b'  # Abbreviations
        ]

        for pattern in academic_patterns:
            if re.search(pattern, all_text):
                academic_score += 0.15

        confidence_factors.append(min(academic_score, 1.0))

        # Calculate final confidence as weighted average
        if confidence_factors:
            return sum(confidence_factors) / len(confidence_factors)
        else:
            return 0.5  # Default moderate confidence

    def _validate_academic_table(self, table_data: List[List[str]]) -> bool:
        """Validate if extracted data represents a valid academic table."""
        if not table_data or len(table_data) < 2:
            return False

        # Check minimum requirements
        min_cols = 2
        min_rows = 2

        if len(table_data) < min_rows:
            return False

        # Check if most rows have reasonable column count
        col_counts = [len(row) for row in table_data]
        avg_cols = sum(col_counts) / len(col_counts)

        if avg_cols < min_cols:
            return False

        # Check for content quality
        total_cells = sum(col_counts)
        non_empty_cells = sum(
            1 for row in table_data for cell in row if cell.strip())

        # At least 60% of cells should have content
        if non_empty_cells < total_cells * 0.6:
            return False

        return True

    def _split_by_positions(self, line: str, positions: List[int]) -> List[str]:
        """Split line by specific character positions with improved boundary detection."""
        if not positions or not line.strip():
            return [line.strip()] if line.strip() else []

        columns = []
        start = 0

        for pos in sorted(positions):
            if pos < len(line):
                # Extract column content
                column_text = line[start:pos].strip()
                if column_text:  # Only add non-empty columns
                    columns.append(column_text)
                start = pos

                # Skip whitespace after the separator
                while start < len(line) and line[start].isspace():
                    start += 1

        # Add final column if there's remaining content
        if start < len(line):
            final_column = line[start:].strip()
            if final_column:
                columns.append(final_column)

        # Ensure we have at least some content
        return columns if columns else [line.strip()]

    def _split_by_patterns(self, line: str, patterns: List[Dict[str, Any]]) -> List[str]:
        """Split line based on identified content patterns with improved robustness."""
        if not patterns or not line.strip():
            return [line.strip()] if line.strip() else []

        columns = []
        remaining = line.strip()

        # Sort patterns by their average position
        sorted_patterns = sorted(patterns, key=lambda x: x['avg_position'])

        # Define regex patterns for each pattern type (algorithmic and flexible)
        pattern_regexes = {
            'author_reference': r'[A-Za-z][^,\d]*?\bet al\.?[^,]*',
            'year_parentheses': r'\([^)]*\d{4}[^)]*\)',
            'dataset_parentheses': r'\([^)]*(?:dataset|data|corpus|benchmark)[^)]*\)',
            'percentage': r'\d+\.?\d*\s*%',
            'numbers_with_units': r'\d+\.?\d*[MKBGTmkμnpf]?[BWHzsFLVA]?\b',
            'scientific_notation': r'\d+\.?\d*[eE][+-]?\d+',
            'technical_terms': r'\b[A-Z][a-zA-Z]*(?:[A-Z][a-zA-Z]*){1,3}\b',
            'acronyms': r'\b[A-Z]{2,6}\b(?:-\d+)?',
            'versioned_terms': r'\b[A-Za-z]+[-_]?\d+(?:\.\d+)*\b',
            'hyphenated_terms': r'\b[A-Za-z]+(?:-[A-Za-z]+){1,3}\b'
        }

        last_end = 0

        for pattern_info in sorted_patterns:
            pattern_name = pattern_info['name']
            pattern_regex = pattern_regexes.get(pattern_name, '')

            if pattern_regex:
                # Search from where we left off
                search_text = remaining[last_end:] if last_end < len(
                    remaining) else ""
                match = re.search(pattern_regex, search_text, re.IGNORECASE)

                if match:
                    # Calculate absolute position in the remaining string
                    match_start = last_end + match.start()
                    match_end = last_end + match.end()

                    # Extract content up to and including the match
                    if match_start > last_end:
                        # Add content before the match as a separate column
                        pre_content = remaining[last_end:match_start].strip()
                        if pre_content:
                            columns.append(pre_content)

                    # Add the matched content
                    matched_content = remaining[match_start:match_end].strip()
                    if matched_content:
                        columns.append(matched_content)

                    last_end = match_end

        # Add any remaining content as final column
        if last_end < len(remaining):
            final_content = remaining[last_end:].strip()
            if final_content:
                columns.append(final_content)

        # If no patterns matched, fall back to simple splitting
        if not columns:
            # Try to split on common separators
            if '\t' in line:
                columns = [col.strip()
                           for col in line.split('\t') if col.strip()]
            elif '  ' in line:  # Two or more spaces
                columns = [col.strip()
                           for col in re.split(r'\s{2,}', line) if col.strip()]
            else:
                # Last resort: split into reasonable chunks
                words = line.split()
                if len(words) <= 4:
                    columns = words
                else:
                    # Group words intelligently
                    mid = len(words) // 2
                    columns = [' '.join(words[:mid]), ' '.join(words[mid:])]

        return columns

    def _split_by_word_groups(self, line: str, target_columns: int) -> List[str]:
        """Split line into word groups with content-aware distribution."""
        words = line.split()
        if not words:
            return []

        if len(words) <= target_columns:
            # Pad with empty strings if needed
            result = words[:]
            while len(result) < target_columns:
                result.append('')
            return result

        # Smart distribution based on content patterns
        columns = []

        # Identify potential column boundaries based on content patterns
        boundaries = []

        for i, word in enumerate(words[:-1]):
            next_word = words[i + 1]

            # Boundary indicators:
            # 1. Number followed by text
            if re.match(r'^\d+\.?\d*[%]?$', word) and re.match(r'^[A-Za-z]', next_word):
                boundaries.append(i + 1)
            # 2. Citation pattern (author et al.) followed by different content
            elif 'et al.' in word and not 'et al.' in next_word:
                boundaries.append(i + 1)
            # 3. Year in parentheses followed by different content
            elif re.search(r'\(\d{4}\)', word) and not re.search(r'\(\d{4}\)', next_word):
                boundaries.append(i + 1)
            # 4. Technical terms (acronyms, CamelCase, versioned) followed by different type
            elif (re.match(r'^(?:[A-Z]{2,6}(?:-\d+)?|[A-Z][a-zA-Z]*(?:[A-Z][a-zA-Z]*){1,3}|[A-Za-z]+[-_]?\d+(?:\.\d+)*)', word, re.IGNORECASE)
                  and not re.match(r'^(?:[A-Z]{2,6}(?:-\d+)?|[A-Z][a-zA-Z]*(?:[A-Z][a-zA-Z]*){1,3}|[A-Za-z]+[-_]?\d+(?:\.\d+)*)', next_word, re.IGNORECASE)):
                boundaries.append(i + 1)

        # If we found good boundaries, use them
        if boundaries:
            # Select the best boundaries to achieve target columns
            if len(boundaries) >= target_columns - 1:
                # Use the first (target_columns - 1) boundaries
                selected_boundaries = boundaries[:target_columns - 1]
            else:
                # Use all boundaries and add more if needed
                selected_boundaries = boundaries[:]
                remaining_splits = target_columns - len(boundaries) - 1
                if remaining_splits > 0:
                    # Distribute remaining splits evenly
                    words_per_remaining = len(words) // (remaining_splits + 1)
                    for i in range(remaining_splits):
                        pos = (i + 1) * words_per_remaining
                        if pos < len(words) and pos not in selected_boundaries:
                            selected_boundaries.append(pos)

            selected_boundaries.sort()

            # Create columns based on boundaries
            start_idx = 0
            for boundary in selected_boundaries:
                if start_idx < len(words):
                    column = ' '.join(words[start_idx:boundary])
                    columns.append(column)
                    start_idx = boundary

            # Add final column
            if start_idx < len(words):
                column = ' '.join(words[start_idx:])
                columns.append(column)

        else:
            # Fallback: distribute words evenly
            words_per_col = len(words) // target_columns
            remainder = len(words) % target_columns

            start_idx = 0
            for i in range(target_columns):
                # Add one extra word to first 'remainder' columns
                col_size = words_per_col + (1 if i < remainder else 0)
                end_idx = start_idx + col_size

                if start_idx < len(words):
                    column = ' '.join(
                        words[start_idx:min(end_idx, len(words))])
                    columns.append(column)
                    start_idx = end_idx
                else:
                    columns.append('')

        # Ensure we have exactly target_columns
        while len(columns) < target_columns:
            columns.append('')

        return columns[:target_columns]

    def _looks_like_header_row(self, line: str) -> bool:
        """Check if a line looks like a table header."""
        line_lower = line.lower()

        # Use algorithmic patterns instead of hardcoded terms
        # Primary column header indicators (algorithmic detection)
        primary_patterns = [
            # Medium-length words (likely descriptive terms)
            r'\b[a-z]{4,12}\b',
            r'\b[A-Z]{2,}\s+\d{4}\b',  # Dataset patterns like "ISIC 2017"
            r'\b[A-Z][a-z]+[A-Z][a-z]*\b',  # CamelCase terms
            r'\b\w+[-_]\w+\b',  # Hyphenated or underscore terms
            r'\b[A-Z][a-z]{2,8}\b',  # Capitalized terms
        ]

        # Metric sub-header indicators (short abbreviations, repeated patterns)
        metric_patterns = [
            # Repeated short terms like "DSC SE SP ACC"
            r'\b[a-z]{2,4}\b(?:\s+[a-z]{2,4}\b){2,}',
            # Repeated caps like "DSC SE SP ACC"
            r'\b[A-Z]{2,4}\b(?:\s+[A-Z]{2,4}\b){2,}',
        ]

        words = line_lower.split()

        # Count matches using algorithmic patterns
        primary_matches = sum(1 for pattern in primary_patterns
                              if re.search(pattern, line))
        metric_matches = sum(1 for pattern in metric_patterns
                             if re.search(pattern, line))

        # Check for dataset/year patterns (like "ISIC 2017", "MNIST", etc.)
        has_dataset_pattern = bool(
            re.search(r'\b[A-Z]{2,}\s+\d{4}\b|\b[A-Z]{2,}\s+\d+\b', line))

        # Check for repeated patterns (sub-headers often repeat metrics)
        unique_words = set(words)
        word_repetition_ratio = len(unique_words) / len(words) if words else 1
        is_repetitive = word_repetition_ratio < 0.6  # Less than 60% unique words

        # Primary header logic:
        # 1. Has primary header patterns OR dataset patterns
        # 2. Not overly repetitive (rules out metric sub-headers)
        # 3. Not purely metrics (avoid "DSC SE SP ACC" type lines)
        is_primary_header = (
            (primary_matches >= 1 or has_dataset_pattern) and
            not is_repetitive and
            (metric_matches <= primary_matches or metric_matches <= 2)
        )

        # Fallback: traditional pattern matching for other types
        total_matches = primary_matches + metric_matches
        is_traditional_header = (
            total_matches >= 2 and not is_repetitive
        ) or any(pattern in line_lower for pattern in [
            # Only very specific technical terms
            'parameters (m)', 'flops', 'fps', 'throughput'
        ])

        return is_primary_header or is_traditional_header

    # Missing helper methods for PDF-based table extraction
    def _identify_grid_regions(self, blocks: Dict, page_rect) -> List[List[Dict]]:
        """Identify potential grid regions from PDF blocks."""
        # Simplified implementation - group blocks by approximate rows and columns
        regions = []

        # Extract text blocks
        text_blocks = []
        if "blocks" in blocks:
            for block in blocks["blocks"]:
                if "lines" in block:
                    for line in block["lines"]:
                        if "spans" in line:
                            for span in line["spans"]:
                                if span.get("text", "").strip():
                                    text_blocks.append({
                                        'text': span["text"],
                                        'bbox': span.get("bbox", [0, 0, 0, 0]),
                                        'x': span.get("bbox", [0, 0, 0, 0])[0],
                                        'y': span.get("bbox", [0, 0, 0, 0])[1]
                                    })

        # Group blocks into potential table regions
        if text_blocks:
            # Sort by y-coordinate (top to bottom)
            text_blocks.sort(key=lambda b: b['y'])

            # Group into rows based on y-coordinate proximity
            tolerance = 10  # pixels
            rows = []
            current_row = [text_blocks[0]] if text_blocks else []

            for block in text_blocks[1:]:
                if abs(block['y'] - current_row[0]['y']) <= tolerance:
                    current_row.append(block)
                else:
                    if len(current_row) > 1:  # Only consider rows with multiple elements
                        rows.append(current_row)
                    current_row = [block]

            if len(current_row) > 1:
                rows.append(current_row)

            # If we have multiple rows that look tabular, consider it a region
            if len(rows) >= 2:
                regions.append(rows)

        return regions

    def _analyze_grid_structure(self, region: List[List[Dict]]) -> List[List[str]]:
        """Analyze grid structure to extract table data."""
        table_data = []

        for row in region:
            # Sort row elements by x-coordinate (left to right)
            row.sort(key=lambda b: b['x'])
            row_data = [block['text'].strip()
                        for block in row if block['text'].strip()]
            if row_data:
                table_data.append(row_data)

        return table_data

    def _validate_table_structure(self, table_data: List[List[str]]) -> bool:
        """Validate if the extracted data represents a valid table structure."""
        if not table_data or len(table_data) < 2:
            return False

        # Check if rows have reasonably consistent column counts
        col_counts = [len(row) for row in table_data]
        avg_cols = sum(col_counts) / len(col_counts)
        consistent_rows = sum(
            1 for count in col_counts if abs(count - avg_cols) <= 2)

        # 70% of rows should be consistent
        return consistent_rows >= len(table_data) * 0.7

    def _calculate_table_confidence(self, table_data: List[List[str]]) -> float:
        """Calculate confidence score for extracted table."""
        if not table_data:
            return 0.0

        factors = []

        # Factor 1: Row consistency
        col_counts = [len(row) for row in table_data]
        if col_counts:
            max_cols = max(col_counts)
            min_cols = min(col_counts)
            consistency = min_cols / max_cols if max_cols > 0 else 0
            factors.append(consistency)

        # Factor 2: Content density
        total_cells = sum(col_counts)
        non_empty_cells = sum(
            1 for row in table_data for cell in row if cell.strip())
        density = non_empty_cells / total_cells if total_cells > 0 else 0
        factors.append(density)

        # Factor 3: Numerical content (common in tables)
        numeric_content = sum(1 for row in table_data for cell in row
                              if re.search(r'\d+\.?\d*', cell))
        numeric_ratio = numeric_content / total_cells if total_cells > 0 else 0
        factors.append(min(numeric_ratio * 2, 1.0))  # Cap at 1.0

        return sum(factors) / len(factors) if factors else 0.5

    def _get_structured_text_lines(self, page) -> List[Dict]:
        """Extract structured text lines from page."""
        lines = []

        try:
            blocks = page.get_text("dict")
            if "blocks" in blocks:
                for block in blocks["blocks"]:
                    if "lines" in block:
                        for line in block["lines"]:
                            line_text = ""
                            line_bbox = None

                            if "spans" in line:
                                for span in line["spans"]:
                                    if span.get("text", "").strip():
                                        line_text += span["text"] + " "
                                        if line_bbox is None:
                                            line_bbox = span.get(
                                                "bbox", [0, 0, 0, 0])

                            if line_text.strip():
                                lines.append({
                                    'text': line_text.strip(),
                                    'bbox': line_bbox or [0, 0, 0, 0],
                                    'y': line_bbox[1] if line_bbox else 0
                                })
        except Exception as e:
            self.logger.warning(
                f"Failed to extract structured text lines: {e}")

        return lines

    def _find_aligned_text_regions(self, text_lines: List[Dict]) -> List[List[Dict]]:
        """Find regions of aligned text that might be tables."""
        regions = []

        if not text_lines:
            return regions

        # Sort lines by y-coordinate
        text_lines.sort(key=lambda l: l['y'])

        # Group lines that might form a table
        current_region = []
        prev_y = None

        for line in text_lines:
            # Check if this line has multiple "words" separated by significant spaces
            text = line['text']
            if self._looks_like_table_row(text):
                # Lines close together
                if prev_y is None or abs(line['y'] - prev_y) < 50:
                    current_region.append(line)
                else:
                    if len(current_region) >= 3:  # Minimum rows for a table
                        regions.append(current_region)
                    current_region = [line]
                prev_y = line['y']
            else:
                if len(current_region) >= 3:
                    regions.append(current_region)
                current_region = []
                prev_y = None

        # Add final region
        if len(current_region) >= 3:
            regions.append(current_region)

        return regions

    def _parse_aligned_table(self, region: List[Dict]) -> List[List[str]]:
        """Parse aligned text region into table data."""
        table_data = []

        for line_dict in region:
            text = line_dict['text']
            # Use existing text parsing logic
            if self._looks_like_table_row(text):
                # Split by multiple spaces or tabs
                if '\t' in text:
                    row_data = [cell.strip()
                                for cell in text.split('\t') if cell.strip()]
                else:
                    row_data = [cell.strip() for cell in re.split(
                        r'\s{2,}', text) if cell.strip()]

                if row_data:
                    table_data.append(row_data)

        return table_data

    def _calculate_alignment_confidence(self, region: List[Dict]) -> float:
        """Calculate confidence for aligned text region."""
        if not region:
            return 0.0

        # Simple confidence based on consistency of content
        table_data = self._parse_aligned_table(region)
        return self._calculate_table_confidence(table_data)

    def _extract_table_lines(self, drawings: List) -> List[Dict]:
        """Extract lines that might form table borders."""
        lines = []

        # Look for horizontal and vertical lines in drawings
        for drawing in drawings:
            if drawing.get('type') == 'l':  # Line
                start = drawing.get('start', [0, 0])
                end = drawing.get('end', [0, 0])

                # Determine if horizontal or vertical
                is_horizontal = abs(start[1] - end[1]) < 5
                is_vertical = abs(start[0] - end[0]) < 5

                if is_horizontal or is_vertical:
                    lines.append({
                        'start': start,
                        'end': end,
                        'horizontal': is_horizontal,
                        'vertical': is_vertical
                    })

        return lines

    def _build_grid_from_lines(self, lines: List[Dict]) -> Optional[Dict]:
        """Build grid structure from detected lines."""
        if not lines:
            return None

        # Group horizontal and vertical lines
        h_lines = [l for l in lines if l['horizontal']]
        v_lines = [l for l in lines if l['vertical']]

        if len(h_lines) >= 2 and len(v_lines) >= 2:
            # Find intersections to form grid
            return {
                'horizontal_lines': h_lines,
                'vertical_lines': v_lines,
                'rows': len(h_lines) - 1,
                'cols': len(v_lines) - 1
            }

        return None

    def _extract_text_from_grid(self, page, grid_structure: Dict) -> List[List[str]]:
        """Extract text content from grid cells."""
        # Simplified implementation - just return empty for now
        # In a full implementation, this would extract text within each grid cell
        return []

    def _estimate_column_count_from_words(self, lines: List[str]) -> int:
        """Estimate reasonable column count from word distribution."""
        if not lines:
            return 2

        word_counts = [len(line.split()) for line in lines]
        if word_counts:
            avg_words = sum(word_counts) / len(word_counts)
            # Estimate columns based on average word count
            if avg_words <= 4:
                return 2
            elif avg_words <= 8:
                return 3
            elif avg_words <= 12:
                return 4
            else:
                return min(5, int(avg_words / 3))

        return 2
