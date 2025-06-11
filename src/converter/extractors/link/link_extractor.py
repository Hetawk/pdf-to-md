"""Link extraction functionality for PDF processing."""

import re
from typing import Dict, List, Any, Optional

from ..base import BaseExtractor


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
