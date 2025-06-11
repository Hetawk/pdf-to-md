"""Individual bibliographic source searchers."""

import re
import logging
import requests
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional, List
from urllib.parse import quote
from datetime import datetime


class BaseSearcher:
    """Base class for bibliographic searchers."""

    def __init__(self, session):
        self.session = session

    def _is_good_match(self, original_title: str, found_title: str, threshold: float = 0.8) -> bool:
        """Check if titles match sufficiently."""
        if not found_title:
            return False

        # Simple similarity check
        original_words = set(original_title.lower().split())
        found_words = set(found_title.lower().split())

        if not original_words:
            return False

        intersection = original_words.intersection(found_words)
        similarity = len(intersection) / len(original_words)

        return similarity >= threshold


class CrossRefSearcher(BaseSearcher):
    """Search Crossref for paper metadata."""

    def __init__(self, session, credentials):
        super().__init__(session)
        self.credentials = credentials

    def search(self, title: str, authors: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Search Crossref for paper metadata."""
        try:
            # Construct query
            query_parts = [title]
            if authors:
                query_parts.extend(authors[:2])  # Use first 2 authors

            query = ' '.join(query_parts)

            params = {
                'query': query,
                'rows': 5,
                'sort': 'relevance'
            }

            url = 'https://api.crossref.org/works'
            response = self.session.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                items = data.get('message', {}).get('items', [])

                # Find best match
                for item in items:
                    if self._is_good_match(title, item.get('title', [''])[0]):
                        return self._format_metadata(item)

        except Exception as e:
            logging.warning(f"Crossref search failed: {e}")

        return None

    def _format_metadata(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Format Crossref metadata."""
        metadata = {
            'source': 'crossref',
            'title': item.get('title', [''])[0],
            'doi': item.get('DOI'),
            'year': None,
            'month': None,
            'authors': [],
            'venue': None,
            'abstract': item.get('abstract'),
            'citation_count': item.get('is-referenced-by-count'),
            'publisher': item.get('publisher'),
            'type': item.get('type'),
            'volume': item.get('volume'),
            'issue': item.get('issue'),
            'pages': None,
            'language': item.get('language'),
            'url': f"https://doi.org/{item.get('DOI')}" if item.get('DOI') else None
        }

        # Enhanced date extraction with month
        date_info = item.get(
            'published-print') or item.get('published-online') or item.get('created')
        if date_info and 'date-parts' in date_info:
            date_parts = date_info['date-parts'][0] if date_info['date-parts'] else []
            if len(date_parts) >= 1:
                metadata['year'] = date_parts[0]
            if len(date_parts) >= 2:
                month_names = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
                               'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
                if 1 <= date_parts[1] <= 12:
                    metadata['month'] = month_names[date_parts[1] - 1]

        # Extract authors
        for author in item.get('author', []):
            given = author.get('given', '')
            family = author.get('family', '')
            if family:
                full_name = f"{given} {family}".strip()
                metadata['authors'].append(full_name)

        # Extract venue
        if 'container-title' in item:
            metadata['venue'] = item['container-title'][0] if item['container-title'] else None

        # Enhanced pages extraction
        if 'page' in item:
            metadata['pages'] = item['page']

        return metadata


class ArxivSearcher(BaseSearcher):
    """Search arXiv for paper metadata."""

    def search(self, title: str, arxiv_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Search arXiv for paper metadata."""
        try:
            if arxiv_id:
                url = f'http://export.arxiv.org/api/query?id_list={arxiv_id}'
            else:
                # Search by title
                query = quote(f'ti:"{title}"')
                url = f'http://export.arxiv.org/api/query?search_query={query}&max_results=5'

            response = self.session.get(url, timeout=10)

            if response.status_code == 200:
                return self._parse_response(response.text, title)

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                requests.exceptions.ProxyError) as e:
            logging.info(
                f"arXiv unavailable due to network configuration: {type(e).__name__}")
            return None
        except Exception as e:
            logging.warning(f"arXiv search failed: {e}")

        return None

    def _parse_response(self, xml_text: str, original_title: str) -> Optional[Dict[str, Any]]:
        """Parse arXiv XML response."""
        try:
            root = ET.fromstring(xml_text)
            entries = root.findall('.//{http://www.w3.org/2005/Atom}entry')

            for entry in entries:
                title = entry.find('.//{http://www.w3.org/2005/Atom}title')
                if title is not None and self._is_good_match(original_title, title.text):
                    return self._format_entry(entry)

        except Exception as e:
            logging.warning(f"Failed to parse arXiv response: {e}")

        return None

    def _format_entry(self, entry) -> Dict[str, Any]:
        """Format arXiv entry metadata."""
        metadata = {
            'source': 'arxiv',
            'title': None,
            'arxiv_id': None,
            'year': None,
            'month': None,
            'authors': [],
            'abstract': None,
            'categories': [],
            'url': None,
            'language': 'english'
        }

        # Extract basic info
        title_elem = entry.find('.//{http://www.w3.org/2005/Atom}title')
        if title_elem is not None:
            metadata['title'] = title_elem.text.strip()

        # Extract arXiv ID from URL
        id_elem = entry.find('.//{http://www.w3.org/2005/Atom}id')
        if id_elem is not None:
            arxiv_url = id_elem.text
            metadata['url'] = arxiv_url
            # Extract ID from URL like http://arxiv.org/abs/1234.5678v1
            arxiv_match = re.search(r'abs/(\d{4}\.\d{4,5})', arxiv_url)
            if arxiv_match:
                metadata['arxiv_id'] = arxiv_match.group(1)

        # Enhanced date extraction with month
        published_elem = entry.find(
            './/{http://www.w3.org/2005/Atom}published')
        if published_elem is not None:
            try:
                published_date = published_elem.text
                metadata['year'] = int(published_date[:4])
                # Extract month
                date_obj = datetime.fromisoformat(
                    published_date.replace('Z', '+00:00'))
                month_names = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
                               'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
                metadata['month'] = month_names[date_obj.month - 1]
            except (ValueError, TypeError):
                pass

        # Enhanced categories extraction
        primary_cat = entry.find(
            './/{http://arxiv.org/schemas/atom}primary_category')
        if primary_cat is not None:
            metadata['categories'].append(primary_cat.get('term'))

        # Also get secondary categories
        categories = entry.findall('.//{http://www.w3.org/2005/Atom}category')
        for cat in categories:
            term = cat.get('term')
            if term and term not in metadata['categories']:
                metadata['categories'].append(term)

        return metadata


class SemanticScholarSearcher(BaseSearcher):
    """Search Semantic Scholar for paper metadata."""

    def __init__(self, session, credentials):
        super().__init__(session)
        self.credentials = credentials

    def search(self, title: str, doi: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Search Semantic Scholar for paper metadata."""
        try:
            headers = {}
            if self.credentials.get('semantic_scholar_key'):
                headers['x-api-key'] = self.credentials['semantic_scholar_key']

            if doi:
                url = f'https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}'
            else:
                # Search by title
                params = {'query': title, 'limit': 5}
                url = 'https://api.semanticscholar.org/graph/v1/paper/search'
                response = self.session.get(
                    url, params=params, headers=headers, timeout=10)

                if response.status_code == 429:  # Rate limited
                    logging.warning("Semantic Scholar rate limit reached")
                    return None
                elif response.status_code != 200:
                    logging.debug(
                        f"Semantic Scholar search failed with status {response.status_code}")
                    return None

                data = response.json()
                papers = data.get('data', [])

                for paper in papers:
                    if self._is_good_match(title, paper.get('title', '')):
                        paper_id = paper.get('paperId')
                        if paper_id:
                            url = f'https://api.semanticscholar.org/graph/v1/paper/{paper_id}'
                            break
                else:
                    return None

            # Get detailed paper info
            params = {
                'fields': 'title,authors,year,venue,doi,arxivId,abstract,citationCount,influentialCitationCount,references,citations'
            }

            response = self.session.get(
                url, params=params, headers=headers, timeout=10)

            if response.status_code == 200:
                return self._format_metadata(response.json())
            elif response.status_code == 429:
                logging.warning(
                    "Semantic Scholar rate limit reached on detailed fetch")
                return None
            else:
                logging.debug(
                    f"Semantic Scholar detailed fetch failed with status {response.status_code}")
                return None

        except (requests.exceptions.SSLError, requests.exceptions.ProxyError,
                requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            logging.info(
                f"Semantic Scholar unavailable due to network configuration: {type(e).__name__}")
            return None
        except Exception as e:
            logging.warning(f"Semantic Scholar search failed: {e}")

        return None

    def _format_metadata(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Format Semantic Scholar metadata."""
        metadata = {
            'source': 'semantic_scholar',
            'title': data.get('title'),
            'doi': data.get('doi'),
            'arxiv_id': data.get('arxivId'),
            'year': data.get('year'),
            'authors': [],
            'venue': data.get('venue'),
            'abstract': data.get('abstract'),
            'citation_count': data.get('citationCount'),
            'influential_citation_count': data.get('influentialCitationCount'),
            'reference_count': len(data.get('references', [])),
            'language': 'english',
            'url': f"https://www.semanticscholar.org/paper/{data.get('paperId')}" if data.get('paperId') else None
        }

        # Extract authors with potential affiliation info
        for author in data.get('authors', []):
            if author.get('name'):
                metadata['authors'].append(author['name'])

        return metadata
