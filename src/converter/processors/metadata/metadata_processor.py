"""Metadata extraction and processing functionality for PDF processing."""

import logging
from typing import Dict, Any, Optional
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
