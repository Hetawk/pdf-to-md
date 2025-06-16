"""Metadata enricher wrapper for bibliographic enrichment."""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

from ..utils.fitz_import import fitz  # Safe PyMuPDF import
from .enricher import BibliographicEnricher


class MetadataEnricher:
    """Wrapper class for metadata extraction and enrichment."""

    def __init__(self, config=None):
        """Initialize the metadata enricher."""
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        self.bibliographic_enricher = BibliographicEnricher(config)

    def extract_metadata(self, pdf_path: str) -> Dict[str, Any]:
        """Extract basic metadata from PDF file."""
        metadata = {
            'title': '',
            'author': '',
            'subject': '',
            'creator': '',
            'producer': '',
            'creation_date': '',
            'modification_date': '',
            'content_text': ''
        }

        try:
            with fitz.open(pdf_path) as doc:
                # Extract PDF metadata
                pdf_metadata = doc.metadata
                metadata.update({
                    'title': pdf_metadata.get('title', ''),
                    'author': pdf_metadata.get('author', ''),
                    'subject': pdf_metadata.get('subject', ''),
                    'creator': pdf_metadata.get('creator', ''),
                    'producer': pdf_metadata.get('producer', ''),
                    'creation_date': pdf_metadata.get('creationDate', ''),
                    'modification_date': pdf_metadata.get('modDate', '')
                })

                # Extract text content from first few pages for enrichment
                content_pages = min(3, len(doc))  # Use first 3 pages
                content_text = ""
                for page_num in range(content_pages):
                    page = doc[page_num]
                    content_text += page.get_text()

                # Limit text length
                metadata['content_text'] = content_text[:5000]

                # If no title in metadata, try to extract from content
                if not metadata['title'] and content_text:
                    # Simple heuristic: first non-empty line is likely the title
                    lines = content_text.split('\n')
                    for line in lines[:10]:  # Check first 10 lines
                        line = line.strip()
                        if line and len(line) > 10 and not line.isupper():
                            # Limit title length
                            metadata['title'] = line[:200]
                            break

                self.logger.info(
                    f"Extracted metadata from PDF: title='{metadata['title'][:50]}...'")

        except Exception as e:
            self.logger.warning(f"Failed to extract metadata from PDF: {e}")

        return metadata

    def enrich_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich metadata using bibliographic sources."""
        try:
            title = metadata.get('title', '')
            content_text = metadata.get('content_text', '')

            if not title:
                self.logger.warning("No title available for enrichment")
                return metadata

            # Use the bibliographic enricher
            enriched = self.bibliographic_enricher.enrich_paper_metadata(
                title=title,
                content_text=content_text,
                extracted_metadata=metadata
            )

            # Merge original metadata with enriched data
            enriched['original_metadata'] = metadata

            self.logger.info(f"Enriched metadata for: {title[:50]}...")

            return enriched

        except Exception as e:
            self.logger.warning(f"Failed to enrich metadata: {e}")
            return metadata

    def save_enriched_metadata(self, enriched_metadata: Dict[str, Any], output_path: str):
        """Save enriched metadata to JSON file."""
        try:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(enriched_metadata, f, indent=2,
                          ensure_ascii=False, default=str)

            self.logger.info(f"Saved enriched metadata to: {output_path}")

        except Exception as e:
            self.logger.error(f"Failed to save enriched metadata: {e}")
            raise

    def generate_bibtex(self, enriched_metadata: Dict[str, Any], output_path: str):
        """Generate and save BibTeX entry."""
        try:
            # Generate BibTeX entry
            bibtex_entry = self.bibliographic_enricher.generate_bibtex_entry(
                enriched_metadata)

            if bibtex_entry:
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)

                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(bibtex_entry)

                self.logger.info(
                    f"Generated BibTeX entry saved to: {output_path}")
            else:
                self.logger.warning(
                    "No BibTeX entry could be generated from enriched metadata")

        except Exception as e:
            self.logger.error(f"Failed to generate BibTeX: {e}")
            raise
