"""BibTeX entry generation functionality."""

from typing import Dict, Any, Optional


class BibtexGenerator:
    """Generate BibTeX entries from enriched metadata."""

    def generate_entry(self, enriched_metadata: Dict[str, Any]) -> Optional[str]:
        """Generate BibTeX entry from enriched metadata."""
        # Use the best available source
        bib_data = None
        for source in ['semantic_scholar', 'crossref', 'arxiv']:
            if source in enriched_metadata.get('bibliographic_data', {}):
                bib_data = enriched_metadata['bibliographic_data'][source]
                break

        if not bib_data:
            return None

        # Generate entry
        entry_id = self._generate_bibtex_id(bib_data)
        entry_type = self._determine_entry_type(bib_data)

        bib_entry = f"@{entry_type}{{{entry_id},\n"

        # Core fields
        if bib_data.get('title'):
            bib_entry += f"  title = {{{bib_data['title']}}},\n"

        if bib_data.get('authors'):
            authors_str = ' and '.join(bib_data['authors'])
            bib_entry += f"  author = {{{authors_str}}},\n"

        if bib_data.get('year'):
            bib_entry += f"  year = {{{bib_data['year']}}},\n"

        # Journal/Conference/Venue
        if bib_data.get('venue'):
            venue = bib_data['venue']
            if venue:  # Check if venue is not None
                # Determine if it's a journal or conference
                if any(word in venue.lower() for word in ['conference', 'proceedings', 'workshop', 'symposium', 'meeting']):
                    bib_entry += f"  booktitle = {{{venue}}},\n"
                else:
                    bib_entry += f"  journal = {{{venue}}},\n"

        # Publisher information
        if bib_data.get('publisher'):
            bib_entry += f"  publisher = {{{bib_data['publisher']}}},\n"

        # Volume, Issue, Pages
        if bib_data.get('volume'):
            bib_entry += f"  volume = {{{bib_data['volume']}}},\n"
        if bib_data.get('issue') or bib_data.get('number'):
            issue = bib_data.get('issue') or bib_data.get('number')
            bib_entry += f"  number = {{{issue}}},\n"
        if bib_data.get('pages'):
            bib_entry += f"  pages = {{{bib_data['pages']}}},\n"

        # Enhanced identifiers
        if bib_data.get('doi'):
            bib_entry += f"  doi = {{{bib_data['doi']}}},\n"
        if bib_data.get('arxiv_id'):
            bib_entry += f"  eprint = {{{bib_data['arxiv_id']}}},\n"
            bib_entry += f"  archivePrefix = {{arXiv}},\n"
        if bib_data.get('pmid'):
            bib_entry += f"  pmid = {{{bib_data['pmid']}}},\n"

        # URLs
        if bib_data.get('url'):
            bib_entry += f"  url = {{{bib_data['url']}}},\n"

        # Abstract (optional)
        if bib_data.get('abstract') and len(bib_data['abstract']) < 1000:
            abstract = bib_data['abstract'].replace(
                '\n', ' ').replace('\r', ' ')
            bib_entry += f"  abstract = {{{abstract}}},\n"

        # Keywords/Categories
        if bib_data.get('categories'):
            categories_str = ', '.join(bib_data['categories'])
            bib_entry += f"  keywords = {{{categories_str}}},\n"

        # Citation metrics
        if bib_data.get('citation_count'):
            bib_entry += f"  note = {{Cited by {bib_data['citation_count']} papers}},\n"

        # Language
        if bib_data.get('language'):
            bib_entry += f"  language = {{{bib_data['language']}}},\n"

        # Month
        if bib_data.get('month'):
            bib_entry += f"  month = {{{bib_data['month']}}},\n"

        bib_entry = bib_entry.rstrip(',\n') + "\n}"

        return bib_entry

    def _determine_entry_type(self, bib_data: Dict[str, Any]) -> str:
        """Determine BibTeX entry type based on venue and source."""
        venue = bib_data.get('venue', '').lower(
        ) if bib_data.get('venue') else ''

        if bib_data.get('source') == 'arxiv':
            return 'misc'  # arXiv preprints

        # Enhanced conference detection
        conference_keywords = ['conference', 'proceedings', 'workshop', 'symposium',
                               'meeting', 'congress', 'summit', 'cvpr', 'iclr', 'nips',
                               'icml', 'aaai', 'ijcai', 'acl', 'emnlp', 'iccv', 'eccv']

        if any(keyword in venue for keyword in conference_keywords):
            return 'inproceedings'

        # Enhanced journal detection
        journal_keywords = ['journal', 'transactions', 'letters', 'review', 'reports',
                            'nature', 'science', 'cell', 'plos', 'ieee', 'acm']

        if any(keyword in venue for keyword in journal_keywords):
            return 'article'

        # Book indicators
        if 'book' in venue or 'chapter' in venue:
            return 'inbook'

        return 'article'  # Default

    def _generate_bibtex_id(self, bib_data: Dict[str, Any]) -> str:
        """Generate BibTeX entry ID."""
        if bib_data.get('authors') and bib_data.get('year'):
            first_author = bib_data['authors'][0].split()[-1]  # Last name
            return f"{first_author.lower()}{bib_data['year']}"
        elif bib_data.get('arxiv_id'):
            return f"arxiv{bib_data['arxiv_id'].replace('.', '')}"
        else:
            return "unknown"
