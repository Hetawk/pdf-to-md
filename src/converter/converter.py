"""Main PDF to Markdown converter class."""

import fitz
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from tqdm import tqdm

from ..config import Config
from ..enricher import BibliographicEnricher
from .extractors import (TextExtractor, ImageExtractor, TableExtractor,
                         AdvancedImageExtractor, LinkExtractor, FootnoteExtractor, OCRExtractor)
from .processors import MetadataProcessor, ContentProcessor
from .utils import create_conversion_report, validate_conversion_quality


class PDFToMarkdownConverter:
    """Main converter class for PDF to Markdown conversion."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.setup_logging()

        # Initialize extractors
        self.text_extractor = TextExtractor(self.config)
        self.image_extractor = ImageExtractor(self.config)
        self.advanced_image_extractor = AdvancedImageExtractor(self.config)
        self.table_extractor = TableExtractor(self.config)
        self.link_extractor = LinkExtractor(self.config)
        self.footnote_extractor = FootnoteExtractor(self.config)
        self.ocr_extractor = OCRExtractor(self.config)

        # Initialize processors
        self.metadata_processor = MetadataProcessor(self.config)
        self.content_processor = ContentProcessor(self.config)

        # Initialize bibliographic enricher
        self.bib_enricher = BibliographicEnricher(
            self.config) if self.config.get('enrich_metadata', True) else None

    def setup_logging(self):
        """Setup logging for conversion process."""
        # Create logs directory
        logs_dir = Path("out/logs")
        logs_dir.mkdir(parents=True, exist_ok=True)

        log_file = logs_dir / \
            f"pdf_conversion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        logging.basicConfig(
            level=getattr(logging, self.config.get('log_level', 'INFO')),
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def convert_pdf_to_markdown(self, pdf_path: str, output_path: Optional[str] = None) -> bool:
        """Convert a single PDF to Markdown."""
        if output_path is None:
            # Create out/md-json directory and save markdown files there
            out_dir = Path("out")
            md_json_dir = out_dir / "md-json"
            md_json_dir.mkdir(parents=True, exist_ok=True)
            output_path = md_json_dir / Path(pdf_path).with_suffix('.md').name

        # Always use out directory for images regardless of markdown output location
        output_dir = Path("out")

        try:
            self.logger.info(f"Starting conversion: {pdf_path}")

            # Check file accessibility and size
            if not Path(pdf_path).exists():
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")

            file_size = Path(pdf_path).stat().st_size / (1024 * 1024)  # MB
            max_size = self.config.get('max_file_size_mb', 100)
            if file_size > max_size:
                self.logger.warning(
                    f"Large file detected ({file_size:.1f}MB). Conversion may take time.")

            doc = fitz.open(pdf_path)

            # Check if PDF is password protected
            if doc.needs_pass:
                self.logger.error("PDF is password protected. Cannot convert.")
                doc.close()
                return False

            # Check if PDF is text-extractable
            if not self._handle_corrupted_or_scanned_pdfs(doc):
                self.logger.error("PDF appears to be scanned or corrupted.")
                doc.close()
                return False

            # Extract metadata
            metadata = self.metadata_processor.extract_document_metadata(
                doc) if self.config.get('extract_metadata', True) else {}

            # Analyze document structure
            self.text_extractor.analyze_document_structure(doc)

            markdown_content = []
            current_paragraph = []

            # Extract full text for bibliographic enrichment
            full_text = ""
            for page_num in range(len(doc)):
                full_text += doc[page_num].get_text() + " "

            # Bibliographic enrichment
            enriched_metadata = None
            if self.bib_enricher and self.config.get('enrich_metadata', True):
                try:
                    self.logger.info("Enriching bibliographic metadata...")
                    paper_title = metadata.get(
                        'title', '') or self._extract_title_from_text(full_text)
                    enriched_metadata = self.bib_enricher.enrich_paper_metadata(
                        paper_title, full_text, metadata)

                    # Save both individual and combined BibTeX if requested
                    if self.config.get('generate_bibtex', True) and enriched_metadata:
                        # Save individual BibTeX file
                        bibtex_entry = self.bib_enricher.generate_bibtex_entry(
                            enriched_metadata)
                        if bibtex_entry:
                            individual_bibtex_path = Path(
                                output_path).with_suffix('.bib')
                            with open(individual_bibtex_path, 'w', encoding='utf-8') as f:
                                f.write(
                                    f"% Individual BibTeX entry for: {paper_title}\n")
                                f.write(
                                    f"% Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                                f.write(bibtex_entry)
                            self.logger.info(
                                f"Individual BibTeX file saved: {individual_bibtex_path}")

                        # Save enriched metadata for later combined BibTeX generation
                        enriched_path = Path(
                            output_path).with_suffix('.enriched.json')
                        with open(enriched_path, 'w', encoding='utf-8') as f:
                            json.dump(enriched_metadata, f,
                                      indent=2, ensure_ascii=False)

                except Exception as e:
                    self.logger.warning(
                        f"Bibliographic enrichment failed: {e}")

            # Add enhanced frontmatter with enriched metadata
            if self.config.get('extract_metadata', True) and (metadata.get('title') or metadata.get('author') or enriched_metadata):
                frontmatter = self.content_processor.create_frontmatter(
                    metadata, enriched_metadata)
                markdown_content.extend(frontmatter)

            # Add table of contents if available
            if self.config.get('extract_metadata', True):
                toc = self.metadata_processor.extract_table_of_contents(doc)
                if toc:
                    markdown_content.append(toc)

            # Process pages with enhanced extraction
            all_page_data = []
            total_images = 0
            total_tables = 0
            total_footnotes = 0

            # Create output subdirectories
            images_dir = output_dir / "images"
            images_dir.mkdir(parents=True, exist_ok=True)

            # Progress bar for pages
            page_iterator = range(len(doc))
            if self.config.get('show_progress', False):
                page_iterator = tqdm(page_iterator, desc="Processing pages")

            for page_num in page_iterator:
                page = doc[page_num]
                self.logger.debug(f"Processing page {page_num + 1}/{len(doc)}")

                # Process page with enhanced extraction
                page_data = self._process_page(page, page_num, output_dir)
                all_page_data.append(page_data)

                # Accumulate statistics
                total_images += len(page_data['images'])
                total_tables += len(page_data['tables'])
                total_footnotes += len(page_data['footnotes'])

                # Add page content to markdown
                if page_data['content']:
                    markdown_content.extend(page_data['content'])

            # Add bibliographic section if enriched metadata available
            if enriched_metadata and self.config.get('show_bibliography', True):
                bib_section = self.content_processor.create_bibliography_section(
                    enriched_metadata)
                if bib_section:
                    markdown_content.append("\n---\n")  # Separator
                    markdown_content.append(bib_section)

            final_content = '\n\n'.join(markdown_content)

            # Post-process content
            final_content = self.content_processor.post_process_content(
                final_content)

            # Validate conversion quality with enhanced metrics
            quality_metrics = validate_conversion_quality(doc, final_content)

            # Add enhanced extraction statistics
            quality_metrics.update({
                'total_images_extracted': total_images,
                'total_tables_extracted': total_tables,
                'total_footnotes_extracted': total_footnotes,
                'pages_with_ocr': sum(1 for pd in all_page_data if pd['is_scanned']),
                'pages_with_tables': sum(1 for pd in all_page_data if pd['tables']),
                'pages_with_images': sum(1 for pd in all_page_data if pd['images']),
                'total_external_links': sum(len(pd['links'].get('external_links', [])) for pd in all_page_data),
                'total_citations': sum(len(pd['links'].get('citations', [])) for pd in all_page_data)
            })

            # Add enrichment info to quality metrics
            if enriched_metadata:
                quality_metrics['enrichment_sources'] = enriched_metadata.get(
                    'enrichment_sources', [])
                quality_metrics['has_bibliographic_data'] = bool(
                    enriched_metadata.get('bibliographic_data'))

            # Write to file with error handling
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(final_content)
                self.logger.info(f"Markdown saved: {output_path}")
            except UnicodeEncodeError:
                # Fallback: remove problematic characters
                clean_content = final_content.encode(
                    'utf-8', errors='ignore').decode('utf-8')
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(clean_content)
                self.logger.warning(
                    "Some characters were removed due to encoding issues")

            # Create conversion report
            if self.config.get('create_reports', True):
                create_conversion_report(
                    pdf_path, metadata, quality_metrics, output_path)

            doc.close()
            self.logger.info(
                f"Successfully converted: {pdf_path} -> {output_path}")
            return True

        except Exception as e:
            self.logger.error(f"Error converting {pdf_path}: {str(e)}")
            return False

    # ...existing code for other methods...

    def _handle_corrupted_or_scanned_pdfs(self, doc):
        """Handle corrupted or scanned PDFs."""
        try:
            # Check if PDF is text-extractable
            sample_page = doc[0]
            sample_text = sample_page.get_text()

            if len(sample_text.strip()) < 100:  # Very little text extracted
                self.logger.warning(
                    "PDF appears to be scanned or image-based. OCR might be needed.")
                return False

            return True
        except Exception as e:
            self.logger.error(f"Error checking PDF content: {e}")
            return False

    def _extract_title_from_text(self, text: str) -> str:
        """Extract likely title from text."""
        lines = text.split('\n')[:10]  # Check first 10 lines
        for line in lines:
            line = line.strip()
            if len(line) > 10 and len(line) < 200:  # Reasonable title length
                # Check if it looks like a title (not too many numbers/symbols)
                import re
                if re.match(r'^[A-Z].*[a-z]', line) and line.count(' ') > 2:
                    return line
        return "Unknown Title"

    def _process_page(self, page, page_num: int, output_dir: Path) -> Dict[str, Any]:
        """Process a single page with enhanced extraction capabilities."""
        page_data = {
            'content': [],
            'images': [],
            'tables': [],
            'links': {},
            'footnotes': [],
            'is_scanned': False
        }

        try:
            # Check if page is scanned and needs OCR
            is_scanned = self.ocr_extractor.detect_scanned_page(page)
            page_data['is_scanned'] = is_scanned

            if is_scanned and self.config.get('enable_ocr', True):
                self.logger.info(
                    f"Page {page_num} appears to be scanned, applying OCR...")
                ocr_text = self.ocr_extractor.extract_text_from_scanned_page(
                    page, page_num, self.config.get('ocr_language', 'eng'))
                if ocr_text:
                    page_data['content'].append(
                        f"<!-- OCR Content from Page {page_num} -->")
                    page_data['content'].append(ocr_text)
                    return page_data

            # Enhanced image extraction with intelligent naming
            if self.config.get('extract_images', True):
                images = self.advanced_image_extractor.extract_images_from_page(
                    page, page_num, output_dir / "images")
                page_data['images'] = images

                # Create markdown references for images
                for img in images:
                    if img['is_figure']:
                        caption = img.get(
                            'caption', f"Figure {img.get('index', '')} from page {page_num}")
                        page_data['content'].append(
                            f"![{caption}]({img['filename']})")
                        if img.get('caption'):
                            page_data['content'].append(f"*{img['caption']}*")
                    else:
                        page_data['content'].append(
                            f"![{img['type']}]({img['filename']})")

            # Enhanced table extraction with multiple strategies
            if self.config.get('extract_tables', True):
                tables = self.table_extractor.extract_tables_from_page(
                    page, page_num)
                page_data['tables'] = tables

                # Convert tables to markdown and add to content
                for table in tables:
                    markdown_table = self.table_extractor.convert_table_to_markdown(
                        table)
                    if markdown_table:
                        page_data['content'].append(markdown_table)

            # Extract links, citations, and cross-references
            if self.config.get('extract_links', True):
                links = self.link_extractor.extract_links_from_page(
                    page, page_num)
                page_data['links'] = links

                # Process external links
                for link in links['external_links']:
                    if link['text']:
                        page_data['content'].append(
                            f"[{link['text']}]({link['uri']})")

            # Enhanced footnote extraction
            if self.config.get('extract_footnotes', True):
                footnotes = self.footnote_extractor.extract_footnotes_from_page(
                    page, page_num)
                page_data['footnotes'] = footnotes

            # Handle multi-column layout
            if self.config.get('handle_multi_column', True):
                blocks = page.get_text("dict")
                multi_column_text = self.text_extractor.handle_multi_column_text(
                    page, blocks)
                if multi_column_text:
                    for text in multi_column_text:
                        text = self.text_extractor.handle_mathematical_content(
                            text)
                        page_data['content'].append(text)
                    return page_data

            # Regular text extraction
            current_paragraph = []
            blocks = page.get_text("dict")

            for block in blocks["blocks"]:
                if "lines" in block:
                    # Text block processing
                    block_text = ""
                    font_info = None

                    for line in block["lines"]:
                        line_text = ""
                        for span in line["spans"]:
                            text = span["text"]
                            font_size = span["size"]
                            font_flags = span["flags"]
                            font_info = (font_size, font_flags)
                            line_text += text

                        block_text += line_text + " "

                    block_text = self.text_extractor.clean_text(block_text)
                    block_text = self.text_extractor.handle_mathematical_content(
                        block_text)

                    if block_text:
                        # Skip if this is likely part of a table we've already extracted
                        if (len(page_data['tables']) > 0 and
                            self.table_extractor.detect_numerical_patterns(block_text) and
                                len(block_text.split()) <= 5):
                            continue

                        if self.text_extractor.is_likely_heading(block_text, font_info):
                            # Finalize current paragraph
                            if current_paragraph:
                                page_data['content'].append(
                                    '\n'.join(current_paragraph))
                                current_paragraph = []

                            # Add heading
                            level = self.text_extractor.determine_heading_level(
                                font_info)
                            if level:
                                heading = f"{'#' * level} {block_text}"
                                page_data['content'].append(heading)
                            else:
                                page_data['content'].append(f"## {block_text}")
                        else:
                            # Accumulate paragraph text
                            current_paragraph.append(block_text)

            # Add any remaining paragraph
            if current_paragraph:
                paragraph_text = '\n'.join(current_paragraph)

                # Check if this paragraph contains table data before adding it
                if self.config.get('extract_tables', True):
                    text_tables = self.table_extractor.extract_tables_from_text(
                        paragraph_text, page_num)

                    if text_tables:
                        # Add extracted tables to page data
                        page_data['tables'].extend(text_tables)

                        # Convert tables to markdown and add to content
                        for table in text_tables:
                            markdown_table = self.table_extractor.convert_table_to_markdown(
                                table)
                            if markdown_table:
                                page_data['content'].append(markdown_table)

                        # Only add non-table text as regular content
                        remaining_text = self._remove_table_text_from_paragraph(
                            paragraph_text, text_tables)
                        if remaining_text.strip():
                            page_data['content'].append(remaining_text)
                    else:
                        page_data['content'].append(paragraph_text)
                else:
                    page_data['content'].append(paragraph_text)

            # Add footnotes section if any found
            if page_data['footnotes']:
                page_data['content'].append("### Footnotes")
                for footnote in page_data['footnotes']:
                    page_data['content'].append(
                        f"{footnote['number']}. {footnote['content']}")

            # Add citations section if any found
            if page_data['links']['citations']:
                page_data['content'].append("### Citations")
                for citation in page_data['links']['citations']:
                    page_data['content'].append(f"- {citation['text']}")

        except Exception as e:
            self.logger.warning(f"Error processing page {page_num}: {e}")
            # Fallback to basic text extraction
            try:
                text = page.get_text()
                if text.strip():
                    page_data['content'].append(text)
            except:
                page_data['content'].append(
                    f"<!-- Error extracting content from page {page_num} -->")

        return page_data

    def convert_directory(self, directory_path: str):
        """Convert all PDF files in a directory."""
        directory = Path(directory_path)
        pdf_files = list(directory.glob("*.pdf"))

        if not pdf_files:
            self.logger.warning("No PDF files found in the directory.")
            return

        self.logger.info(f"Found {len(pdf_files)} PDF files to convert.")

        # Create out directory structure
        out_dir = Path("out")
        out_dir.mkdir(exist_ok=True)
        md_json_dir = out_dir / "md-json"
        md_json_dir.mkdir(exist_ok=True)

        successful_conversions = 0
        failed_conversions = 0

        # Progress bar for files
        if self.config.get('show_progress', False):
            from tqdm import tqdm
            file_iterator = tqdm(pdf_files, desc="Converting PDFs")
        else:
            file_iterator = pdf_files

        for pdf_file in file_iterator:
            if self.config.get('show_progress', False):
                file_iterator.set_description(f"Converting {pdf_file.name}")

            output_file = md_json_dir / pdf_file.with_suffix('.md').name

            if self.convert_pdf_to_markdown(pdf_file, output_file):
                successful_conversions += 1
            else:
                failed_conversions += 1

        self.logger.info(
            f"Conversion complete: {successful_conversions} successful, {failed_conversions} failed")

        # Create combined markdown file after all conversions
        if successful_conversions > 0:
            self.logger.info("Creating combined markdown file...")
            self._create_combined_markdown(out_dir)

            # Create combined bibliography
            if self.config.get('generate_bibtex', True):
                self.logger.info("Creating combined bibliography...")
                self._create_combined_bibliography(out_dir)

    def _create_combined_markdown(self, output_dir: Path):
        """Create a single combined markdown file from all converted files."""
        try:
            combined_content = []
            combined_content.append("# Research Papers Collection\n")
            combined_content.append(
                f"*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")
            combined_content.append("---\n")

            # Find all markdown files in the md-json subdirectory
            md_json_dir = output_dir / "md-json"
            md_files = list(md_json_dir.glob("*.md"))
            md_files.sort()  # Sort alphabetically

            if not md_files:
                self.logger.warning("No markdown files found to combine")
                return

            self.logger.info(f"Combining {len(md_files)} markdown files")

            # Add table of contents
            combined_content.append("## Table of Contents\n")
            for i, md_file in enumerate(md_files, 1):
                title = md_file.stem.replace('_', ' ').replace('-', ' ')
                anchor = title.lower().replace(' ', '-').replace('_', '-')
                # Remove special characters for anchor
                import re
                anchor = re.sub(r'[^\w\s-]', '', anchor).replace(' ', '-')
                combined_content.append(f"{i}. [{title}](#{anchor})")

            combined_content.append("\n---\n")

            # Combine all papers
            for i, md_file in enumerate(md_files, 1):
                try:
                    with open(md_file, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Create paper title
                    paper_title = md_file.stem.replace(
                        '_', ' ').replace('-', ' ')
                    combined_content.append(f"# {i}. {paper_title}\n")

                    # Remove existing frontmatter if present
                    if content.startswith('---'):
                        parts = content.split('---', 2)
                        if len(parts) >= 3:
                            content = parts[2].strip()

                    # Remove the first h1 heading if it exists (avoid duplicate titles)
                    lines = content.split('\n')
                    if lines and lines[0].startswith('# '):
                        content = '\n'.join(lines[1:])

                    combined_content.append(content)
                    combined_content.append("\n---\n")

                    self.logger.debug(f"Added {md_file.name} to combined file")

                except Exception as e:
                    self.logger.error(f"Error reading {md_file}: {e}")
                    continue

            # Write combined file to main out directory
            combined_path = output_dir / "00_Combined_All_Papers.md"
            final_content = '\n\n'.join(combined_content)

            with open(combined_path, 'w', encoding='utf-8') as f:
                f.write(final_content)

            self.logger.info(
                f"Combined markdown file created: {combined_path}")

            # Create summary statistics
            self._create_summary_statistics(output_dir, md_files)

        except Exception as e:
            self.logger.error(f"Error creating combined markdown: {e}")

    def _create_combined_bibliography(self, output_dir: Path):
        """Create a single combined BibTeX file from all enriched metadata."""
        try:
            md_json_dir = output_dir / "md-json"
            enriched_files = list(md_json_dir.glob("*.enriched.json"))

            if not enriched_files:
                self.logger.warning(
                    "No enriched metadata files found for bibliography")
                return

            self.logger.info(
                f"Creating combined bibliography from {len(enriched_files)} papers")

            combined_bibtex_entries = []
            bibliography_summary = {
                'total_papers': len(enriched_files),
                'successful_enrichments': 0,
                'sources_used': {},
                'generation_date': datetime.now().isoformat(),
                'papers': []
            }

            for enriched_file in enriched_files:
                try:
                    with open(enriched_file, 'r', encoding='utf-8') as f:
                        enriched_metadata = json.load(f)

                    # Generate BibTeX entry
                    if enriched_metadata.get('bibliographic_data'):
                        bibtex_entry = self.bib_enricher.generate_bibtex_entry(
                            enriched_metadata)
                        if bibtex_entry:
                            combined_bibtex_entries.append(bibtex_entry)
                            bibliography_summary['successful_enrichments'] += 1

                            # Track sources used
                            for source in enriched_metadata.get('enrichment_sources', []):
                                bibliography_summary['sources_used'][source] = \
                                    bibliography_summary['sources_used'].get(
                                        source, 0) + 1

                            # Add paper details to summary
                            best_data = None
                            for source in ['semantic_scholar', 'crossref', 'arxiv']:
                                if source in enriched_metadata['bibliographic_data']:
                                    best_data = enriched_metadata['bibliographic_data'][source]
                                    break

                            if best_data:
                                bibliography_summary['papers'].append({
                                    'title': best_data.get('title', 'Unknown'),
                                    'year': best_data.get('year'),
                                    'venue': best_data.get('venue'),
                                    'citation_count': best_data.get('citation_count'),
                                    'doi': best_data.get('doi'),
                                    'arxiv_id': best_data.get('arxiv_id'),
                                    'authors': best_data.get('authors', [])
                                })

                except Exception as e:
                    self.logger.warning(
                        f"Failed to process {enriched_file}: {e}")

            # Write combined BibTeX file
            if combined_bibtex_entries:
                combined_bibtex_path = output_dir / "00_Combined_Bibliography.bib"
                with open(combined_bibtex_path, 'w', encoding='utf-8') as f:
                    f.write(
                        "% Combined Bibliography for Research Papers Collection\n")
                    f.write(
                        f"% Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(
                        f"% Total entries: {len(combined_bibtex_entries)}\n")
                    f.write(
                        "% Individual BibTeX files are also available in md-json/ directory\n\n")

                    for entry in combined_bibtex_entries:
                        f.write(entry + "\n\n")

                self.logger.info(
                    f"Combined BibTeX file saved: {combined_bibtex_path}")

                # Create bibliography summary
                self._create_bibliography_summary(
                    output_dir, bibliography_summary)

            # Keep individual enriched files for reference (don't clean up)
            self.logger.info(
                f"Individual BibTeX files are available in: {md_json_dir}")

        except Exception as e:
            self.logger.error(f"Error creating combined bibliography: {e}")

    def _create_summary_statistics(self, output_dir: Path, md_files: List[Path]):
        """Create a summary statistics file for all papers."""
        try:
            summary = {
                'total_papers': len(md_files),
                'generation_date': datetime.now().isoformat(),
                'papers': []
            }

            total_pages = 0
            total_words = 0
            total_images = 0
            total_tables = 0

            for md_file in md_files:
                # Try to read the corresponding JSON report
                json_file = md_file.with_suffix('.json')
                try:
                    if json_file.exists():
                        with open(json_file, 'r', encoding='utf-8') as f:
                            report = json.load(f)

                        paper_info = {
                            'title': report.get('metadata', {}).get('title', md_file.stem),
                            'file': md_file.name,
                            'pages': report.get('metadata', {}).get('page_count', 0),
                            'words': report.get('quality_metrics', {}).get('word_count', 0),
                            'images': report.get('quality_metrics', {}).get('images_extracted', 0),
                            'tables': report.get('quality_metrics', {}).get('tables_detected', 0),
                            'headings': report.get('quality_metrics', {}).get('headings_detected', 0),
                            'has_math': report.get('quality_metrics', {}).get('has_mathematical_content', False)
                        }

                        summary['papers'].append(paper_info)
                        total_words += paper_info['words']
                        total_pages += paper_info['pages']
                        total_images += paper_info['images']
                        total_tables += paper_info['tables']

                    else:
                        # Fallback: analyze markdown file directly
                        with open(md_file, 'r', encoding='utf-8') as f:
                            content = f.read()

                        words = len(content.split())
                        images = content.count('![')
                        tables = content.count('|')

                        paper_info = {
                            'title': md_file.stem.replace('_', ' '),
                            'file': md_file.name,
                            'pages': 0,
                            'words': words,
                            'images': images,
                            'tables': tables // 3 if tables > 0 else 0,  # Rough estimate
                            'headings': content.count('#'),
                            'has_math': False
                        }

                        summary['papers'].append(paper_info)
                        total_words += words

                except Exception as e:
                    self.logger.warning(
                        f"Could not read report for {md_file}: {e}")

            summary['totals'] = {
                'total_pages': total_pages,
                'total_words': total_words,
                'total_images': total_images,
                'total_tables': total_tables,
                'papers_with_math': sum(1 for p in summary['papers'] if p.get('has_math', False))
            }

            # Save summary as JSON
            summary_path = output_dir / "00_Summary_Statistics.json"
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)

            self.logger.info(f"Summary statistics saved: {summary_path}")

        except Exception as e:
            self.logger.error(f"Error creating summary: {e}")

    def _create_bibliography_summary(self, output_dir: Path, bibliography_summary: Dict):
        """Create a human-readable bibliography summary."""
        try:
            # Save detailed JSON summary
            summary_json_path = output_dir / "00_Bibliography_Summary.json"
            with open(summary_json_path, 'w', encoding='utf-8') as f:
                json.dump(bibliography_summary, f,
                          indent=2, ensure_ascii=False)

            # Create human-readable markdown summary
            summary_md = []
            summary_md.append("# Bibliography Summary\n")
            summary_md.append(
                f"*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")

            # File locations
            summary_md.append("## File Locations\n")
            summary_md.append(
                "- **Combined BibTeX**: `00_Combined_Bibliography.bib`")
            summary_md.append("- **Individual BibTeX files**: `md-json/*.bib`")
            summary_md.append(
                "- **Individual markdown files**: `md-json/*.md`")
            summary_md.append(
                "- **Individual JSON reports**: `md-json/*.json`")

            # Overall statistics
            summary_md.append("\n## Overall Statistics\n")
            summary_md.append(
                f"- **Total Papers**: {bibliography_summary['total_papers']}")
            summary_md.append(
                f"- **Successfully Enriched**: {bibliography_summary['successful_enrichments']}")
            success_rate = (bibliography_summary['successful_enrichments'] /
                            bibliography_summary['total_papers'] * 100) if bibliography_summary['total_papers'] > 0 else 0
            summary_md.append(f"- **Success Rate**: {success_rate:.1f}%")

            # Sources used
            if bibliography_summary['sources_used']:
                summary_md.append(f"\n## Sources Used\n")
                for source, count in bibliography_summary['sources_used'].items():
                    source_name = source.replace('_', ' ').title()
                    summary_md.append(f"- **{source_name}**: {count} papers")

            # Papers with enriched metadata
            summary_md.append(f"\n## Papers with Bibliographic Data\n")
            summary_md.append(
                "| Title | Year | Venue | Citations | DOI | arXiv | Files |")
            summary_md.append(
                "|-------|------|-------|-----------|-----|-------|-------|")

            for paper in bibliography_summary.get('papers', []):
                title = paper['title'][:30] + \
                    "..." if len(paper['title']) > 30 else paper['title']
                year = paper.get('year', 'N/A')
                venue = paper.get(
                    'venue', 'N/A')[:15] if paper.get('venue') else 'N/A'
                citations = paper.get('citation_count', 'N/A')
                doi = "✓" if paper.get('doi') else "✗"
                arxiv = "✓" if paper.get('arxiv_id') else "✗"

                # Create file links
                safe_title = paper['title'].replace(
                    ' ', '_').replace('/', '_')[:30]
                files = f"[MD](md-json/{safe_title}.md) [BIB](md-json/{safe_title}.bib)"

                summary_md.append(
                    f"| {title} | {year} | {venue} | {citations} | {doi} | {arxiv} | {files} |")

            # Save readable summary
            summary_md_path = output_dir / "00_Bibliography_Report.md"
            with open(summary_md_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(summary_md))

            self.logger.info(
                f"Bibliography summary created: {summary_md_path}")

        except Exception as e:
            self.logger.error(f"Error creating bibliography summary: {e}")

    def _remove_table_text_from_paragraph(self, paragraph_text: str, extracted_tables: List[Dict]) -> str:
        """Remove table content from paragraph text to avoid duplication."""
        if not extracted_tables:
            return paragraph_text

        lines = paragraph_text.split('\n')
        remaining_lines = []

        for line in lines:
            line_is_table_content = False

            # Check if this line was part of any extracted table
            for table in extracted_tables:
                table_data = table.get('data', [])
                for row in table_data:
                    # Check if line contains significant overlap with table row
                    row_text = ' '.join(row).lower()
                    line_lower = line.lower()

                    # Calculate similarity
                    common_words = set(row_text.split()) & set(
                        line_lower.split())
                    if len(common_words) >= 2 or (len(row_text.split()) > 0 and
                                                  len(common_words) / len(row_text.split()) > 0.5):
                        line_is_table_content = True
                        break

                if line_is_table_content:
                    break

            if not line_is_table_content:
                remaining_lines.append(line)

        return '\n'.join(remaining_lines)
