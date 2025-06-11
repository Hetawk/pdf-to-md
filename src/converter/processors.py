"""Content and metadata processors for PDF conversion."""

import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import fitz


class BaseProcessor:
    """Base class for content processors."""

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)


class MetadataProcessor(BaseProcessor):
    """Extract and process document metadata."""

    def extract_document_metadata(self, doc) -> Dict[str, Any]:
        """Extract document metadata and properties."""
        metadata = {}
        try:
            # Basic metadata
            metadata.update({
                'title': doc.metadata.get('title', ''),
                'author': doc.metadata.get('author', ''),
                'subject': doc.metadata.get('subject', ''),
                'creator': doc.metadata.get('creator', ''),
                'producer': doc.metadata.get('producer', ''),
                'creation_date': doc.metadata.get('creationDate', ''),
                'modification_date': doc.metadata.get('modDate', ''),
                'trapped': doc.metadata.get('trapped', ''),
                'encrypted': doc.metadata.get('encrypted', False)
            })

            # Document properties
            # Get PDF version safely
            pdf_version = "1.4"  # Default
            try:
                if hasattr(doc, 'pdf_version') and callable(doc.pdf_version):
                    version_tuple = doc.pdf_version()
                    if version_tuple and len(version_tuple) >= 2:
                        pdf_version = f"{version_tuple[0]}.{version_tuple[1]}"
            except Exception:
                pass  # Use default version

            metadata.update({
                'page_count': len(doc),
                'file_size': 0,  # Will be set by caller
                'is_tagged': doc.is_pdf,
                'has_links': False,
                'has_bookmarks': len(doc.get_toc()) > 0,
                'has_javascript': False,  # Basic check
                'pdf_version': pdf_version
            })

            # Clean up metadata
            for key, value in metadata.items():
                if isinstance(value, str):
                    metadata[key] = value.strip()
                    if metadata[key].startswith('D:'):  # PDF date format
                        try:
                            # Convert PDF date to readable format
                            # Extract YYYYMMDDHHMMSS
                            date_str = metadata[key][2:16]
                            if len(date_str) >= 8:
                                year = date_str[:4]
                                month = date_str[4:6]
                                day = date_str[6:8]
                                metadata[key] = f"{year}-{month}-{day}"
                        except:
                            pass

        except Exception as e:
            self.logger.error(f"Error extracting metadata: {e}")

        return metadata

    def extract_table_of_contents(self, doc) -> Optional[str]:
        """Extract table of contents if available."""
        try:
            toc = doc.get_toc()
            if not toc:
                return None

            toc_lines = ["## Table of Contents\n"]
            for level, title, page_num in toc:
                indent = "  " * (level - 1)
                # Clean title
                title = title.strip()
                if title:
                    toc_lines.append(f"{indent}- {title} (Page {page_num})")

            return '\n'.join(toc_lines) + '\n'

        except Exception as e:
            self.logger.warning(f"Could not extract table of contents: {e}")
            return None


class ContentProcessor(BaseProcessor):
    """Process and format markdown content."""

    def post_process_content(self, content: str) -> str:
        """Post-process the markdown content for better formatting."""
        # Remove excessive empty lines
        content = re.sub(r'\n{3,}', '\n\n', content)

        # Fix spacing around headings
        content = re.sub(r'\n(#+\s)', r'\n\n\1', content)
        content = re.sub(r'(#+\s[^\n]+)\n([^\n#])', r'\1\n\n\2', content)

        # Fix spacing around tables
        content = re.sub(r'\n(\|.*\|)\n([^\n|])', r'\n\1\n\n\2', content)

        # Fix spacing around lists
        content = re.sub(r'\n(-\s)', r'\n\n\1', content)
        content = re.sub(r'(-\s[^\n]+)\n([^\n-])', r'\1\n\n\2', content)

        # Clean up excessive spaces
        content = re.sub(r' {3,}', '  ', content)

        return content.strip()

    def create_frontmatter(self, metadata: Dict[str, Any],
                           enriched_metadata: Optional[Dict[str, Any]] = None) -> List[str]:
        """Create YAML frontmatter for the markdown file."""
        frontmatter = ["---"]

        # Original metadata
        if metadata.get('title'):
            frontmatter.append(f"title: \"{metadata['title']}\"")
        if metadata.get('author'):
            frontmatter.append(f"author: \"{metadata['author']}\"")
        if metadata.get('creation_date'):
            frontmatter.append(f"date: \"{metadata['creation_date']}\"")
        if metadata.get('subject'):
            frontmatter.append(f"subject: \"{metadata['subject']}\"")
        if metadata.get('page_count'):
            frontmatter.append(f"pages: {metadata['page_count']}")

        # Enriched metadata
        if enriched_metadata:
            self._add_enriched_frontmatter(frontmatter, enriched_metadata)

        frontmatter.append("---\n")
        return frontmatter

    def _add_enriched_frontmatter(self, frontmatter: List[str],
                                  enriched_metadata: Dict[str, Any]):
        """Add enriched metadata to frontmatter."""
        for source, data in enriched_metadata.get('bibliographic_data', {}).items():
            if data.get('doi'):
                frontmatter.append(f"doi: \"{data['doi']}\"")
            if data.get('arxiv_id'):
                frontmatter.append(f"arxiv: \"{data['arxiv_id']}\"")
            if data.get('citation_count'):
                frontmatter.append(f"citations: {data['citation_count']}")
            if data.get('year'):
                frontmatter.append(f"year: {data['year']}")
            if data.get('venue'):
                frontmatter.append(f"venue: \"{data['venue']}\"")
            if data.get('authors'):
                authors_yaml = '\n  - '.join([''] + data['authors'])
                frontmatter.append(f"authors:{authors_yaml}")
            break  # Use first available source

    def create_bibliography_section(self, enriched_metadata: Dict[str, Any]) -> str:
        """Create bibliography section with enriched metadata."""
        sections = ["## Bibliographic Information\n"]

        for source, data in enriched_metadata.get('bibliographic_data', {}).items():
            sections.append(f"### {source.replace('_', ' ').title()}\n")

            if data.get('citation_count'):
                sections.append(f"**Citations:** {data['citation_count']}")

            if data.get('doi'):
                sections.append(
                    f"**DOI:** [{data['doi']}](https://doi.org/{data['doi']})")

            if data.get('arxiv_id'):
                sections.append(
                    f"**arXiv:** [{data['arxiv_id']}](https://arxiv.org/abs/{data['arxiv_id']})")

            if data.get('url'):
                sections.append(f"**URL:** {data['url']}")

            if data.get('abstract'):
                sections.append(f"**Abstract:** {data['abstract'][:500]}...")

            sections.append("")  # Empty line
            break  # Use first available source

        return '\n'.join(sections)
