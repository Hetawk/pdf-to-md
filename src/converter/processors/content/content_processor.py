"""Content processing functionality for PDF processing."""

import re
from typing import Dict, Any, List, Optional

from ..metadata.metadata_processor import BaseProcessor


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
