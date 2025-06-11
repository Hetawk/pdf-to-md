"""Main bibliographic enrichment class."""

import os
import time
import logging
import requests
from datetime import datetime
from typing import Dict, Any, Optional, List

from .sources import CrossRefSearcher, ArxivSearcher, SemanticScholarSearcher
from .bibtex_generator import BibtexGenerator
from .utils import extract_identifiers_from_text


class BibliographicEnricher:
    """Handle bibliographic metadata enrichment from various sources."""

    def __init__(self, config=None):
        self.config = config or {}
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'PDF-to-Markdown Converter (mailto:research@example.com)'
        })

        # Set default timeout for all requests
        self.session.timeout = 10

        # Setup credentials from environment
        self.setup_credentials()

        # Initialize searchers
        self.crossref = CrossRefSearcher(self.session, self.credentials)
        self.arxiv = ArxivSearcher(self.session)
        self.semantic_scholar = SemanticScholarSearcher(
            self.session, self.credentials)

        # Initialize BibTeX generator
        self.bibtex_generator = BibtexGenerator()

        # Rate limiting
        self.last_request_time = {}
        self.min_delay = {
            'crossref': 1.0,
            'arxiv': 3.0,
            'pubmed': 1.0,
            'semantic_scholar': 2.0  # Fixed: was 'semantic' now matches usage
        }

    def setup_credentials(self):
        """Setup API credentials from environment variables."""
        self.credentials = {
            'crossref_email': os.getenv('CROSSREF_EMAIL'),
            'crossref_token': os.getenv('CROSSREF_TOKEN'),
            'semantic_scholar_key': os.getenv('SEMANTIC_SCHOLAR_API_KEY'),
            'orcid_id': os.getenv('ORCID_ID'),
            'orcid_token': os.getenv('ORCID_TOKEN'),
            'ieee_key': os.getenv('IEEE_API_KEY'),
            'springer_key': os.getenv('SPRINGER_API_KEY')
        }

        # Add email to session headers if available
        if self.credentials['crossref_email']:
            self.session.headers['mailto'] = self.credentials['crossref_email']

    def rate_limit(self, source: str):
        """Implement rate limiting for API calls."""
        now = time.time()
        if source in self.last_request_time:
            time_since_last = now - self.last_request_time[source]
            # Default to 1 second if source not found
            min_delay = self.min_delay.get(source, 1.0)
            if time_since_last < min_delay:
                time.sleep(min_delay - time_since_last)
        self.last_request_time[source] = time.time()

    def enrich_paper_metadata(self, title: str, content_text: str = "", extracted_metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """Main method to enrich paper metadata from multiple sources."""
        enriched_metadata = {
            'title': title,
            'identifiers': {},
            'bibliographic_data': {},
            'enrichment_sources': [],
            'enrichment_timestamp': datetime.now().isoformat()
        }

        # Extract identifiers from content
        identifiers = extract_identifiers_from_text(content_text)
        enriched_metadata['identifiers'] = identifiers

        # Extract potential authors from extracted metadata
        authors = []
        if extracted_metadata and extracted_metadata.get('author'):
            authors = [extracted_metadata['author']]

        # Try different sources
        sources_to_try = [
            ('semantic_scholar', lambda: self.semantic_scholar.search(
                title, identifiers.get('doi'))),
            ('crossref', lambda: self.crossref.search(title, authors)),
            ('arxiv', lambda: self.arxiv.search(title, identifiers.get('arxiv')))
        ]

        for source_name, search_func in sources_to_try:
            try:
                self.rate_limit(source_name)
                result = search_func()
                if result:
                    enriched_metadata['bibliographic_data'][source_name] = result
                    enriched_metadata['enrichment_sources'].append(source_name)
                    logging.info(
                        f"Successfully enriched metadata from {source_name}")
            except Exception as e:
                logging.warning(
                    f"Failed to enrich from {source_name}: {str(e)}")

        return enriched_metadata

    def generate_bibtex_entry(self, enriched_metadata: Dict[str, Any]) -> Optional[str]:
        """Generate BibTeX entry from enriched metadata."""
        return self.bibtex_generator.generate_entry(enriched_metadata)
