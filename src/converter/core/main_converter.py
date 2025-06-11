"""Main PDF to Markdown converter."""

import fitz
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from tqdm import tqdm

from ...config import Config
from ...enricher import BibliographicEnricher
from .base import BaseConverter

# Import specialized extractors
from ..extractors.text import TextExtractor
from ..extractors.image import ImageExtractor, AdvancedImageExtractor
from ..extractors.table import TableExtractor
from ..extractors.link import LinkExtractor
from ..extractors.footnote import FootnoteExtractor
from ..extractors.ocr import OCRExtractor

# Import processors
from ..processors.metadata import MetadataProcessor
from ..processors.content import ContentProcessor

from ..utils import create_conversion_report, validate_conversion_quality


class PDFToMarkdownConverter(BaseConverter):
    """Main converter class for PDF to Markdown conversion with modular extractors."""

    def __init__(self, config: Optional[Config] = None):
        super().__init__(config)

        # Initialize specialized extractors
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

    def convert_pdf_to_markdown(self, pdf_path: str, output_path: Optional[str] = None) -> bool:
        """Convert a single PDF to Markdown with enhanced extraction."""
        # Validate input
        if not self.validate_input(pdf_path):
            return False

        # Setup output paths
        if output_path is None:
            out_dir = Path("out")
            md_json_dir = out_dir / "md-json"
            md_json_dir.mkdir(parents=True, exist_ok=True)
            output_path = md_json_dir / Path(pdf_path).with_suffix('.md').name

        output_dir = Path("out")
        directories = self.create_output_directories(output_dir)

        try:
            self.logger.info(f"Starting conversion: {pdf_path}")

            # Open and validate PDF
            doc = fitz.open(pdf_path)

            if doc.needs_pass:
                self.logger.error("PDF is password protected. Cannot convert.")
                doc.close()
                return False

            if not self._handle_corrupted_or_scanned_pdfs(doc):
                self.logger.error("PDF appears to be scanned or corrupted.")
                doc.close()
                return False

            # Extract document metadata
            metadata = self._extract_document_metadata(doc)

            # Analyze document structure
            self.text_extractor.analyze_document_structure(doc)

            # Perform bibliographic enrichment
            enriched_metadata = self._perform_bibliographic_enrichment(
                doc, metadata, output_path)

            # Process document content
            markdown_content, page_statistics = self._process_document_content(
                doc, directories)

            # Create final markdown content
            final_content = self._create_final_content(
                metadata, enriched_metadata, markdown_content)

            # Save and report
            success = self._save_and_report(
                final_content, pdf_path, output_path, metadata,
                enriched_metadata, page_statistics, doc)

            doc.close()
            return success

        except Exception as e:
            self.logger.error(f"Error converting {pdf_path}: {str(e)}")
            return False

    def _extract_document_metadata(self, doc) -> Dict[str, Any]:
        """Extract document metadata."""
        if not self.config.get('extract_metadata', True):
            return {}
        return self.metadata_processor.extract_document_metadata(doc)

    def _perform_bibliographic_enrichment(self, doc, metadata: Dict[str, Any],
                                          output_path: str) -> Optional[Dict[str, Any]]:
        """Perform bibliographic enrichment if enabled."""
        if not (self.bib_enricher and self.config.get('enrich_metadata', True)):
            return None

        try:
            self.logger.info("Enriching bibliographic metadata...")

            # Extract full text for enrichment
            full_text = ""
            for page_num in range(len(doc)):
                full_text += doc[page_num].get_text() + " "

            paper_title = metadata.get(
                'title', '') or self._extract_title_from_text(full_text)
            enriched_metadata = self.bib_enricher.enrich_paper_metadata(
                paper_title, full_text, metadata)

            # Save BibTeX entries if requested
            if self.config.get('generate_bibtex', True) and enriched_metadata:
                self._save_bibtex_entries(
                    enriched_metadata, paper_title, output_path)

            return enriched_metadata

        except Exception as e:
            self.logger.warning(f"Bibliographic enrichment failed: {e}")
            return None

    def _process_document_content(self, doc, directories: Dict[str, Path]) -> tuple:
        """Process all document content with enhanced extractors."""
        markdown_content = []
        page_statistics = {
            'total_images': 0,
            'total_tables': 0,
            'total_footnotes': 0,
            'total_links': 0,
            'scanned_pages': 0
        }

        # Add table of contents if available
        if self.config.get('extract_metadata', True):
            toc = self.metadata_processor.extract_table_of_contents(doc)
            if toc:
                markdown_content.append(toc)

        # Process pages with progress tracking
        page_iterator = range(len(doc))
        if self.config.get('show_progress', False):
            page_iterator = tqdm(page_iterator, desc="Processing pages")

        for page_num in page_iterator:
            page = doc[page_num]
            self.logger.debug(f"Processing page {page_num + 1}/{len(doc)}")

            # Process page with all extractors
            page_data = self._process_page(page, page_num, directories['base'])

            # Accumulate statistics
            page_statistics['total_images'] += len(page_data.get('images', []))
            page_statistics['total_tables'] += len(page_data.get('tables', []))
            page_statistics['total_footnotes'] += len(
                page_data.get('footnotes', []))
            page_statistics['total_links'] += sum(len(links)
                                                  for links in page_data.get('links', {}).values())

            if page_data.get('is_scanned', False):
                page_statistics['scanned_pages'] += 1

            # Add page content to markdown
            if page_data.get('content'):
                markdown_content.extend(page_data['content'])

        return markdown_content, page_statistics

    def _process_page(self, page, page_num: int, output_dir: Path) -> Dict[str, Any]:
        """Process a single page with all extractors."""
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

            # Enhanced image extraction
            if self.config.get('extract_images', True):
                images = self.advanced_image_extractor.extract_images_from_page(
                    page, page_num, output_dir / "images")
                page_data['images'] = images

                # Create markdown references for images
                for img in images:
                    if img.get('is_figure'):
                        caption = img.get(
                            'caption', f"Figure {img.get('index', '')} from page {page_num}")
                        page_data['content'].append(
                            f"![{caption}]({img['filename']})")
                        if img.get('caption'):
                            page_data['content'].append(f"*{img['caption']}*")
                    else:
                        page_data['content'].append(
                            f"![{img['type']}]({img['filename']})")

            # Enhanced table extraction
            if self.config.get('extract_tables', True):
                tables = self.table_extractor.extract_tables_from_page(
                    page, page_num)
                page_data['tables'] = tables

                # Convert tables to markdown
                for table in tables:
                    markdown_table = self.table_extractor.convert_table_to_markdown(
                        table)
                    if markdown_table:
                        page_data['content'].append(markdown_table)

            # Extract links and references
            if self.config.get('extract_links', True):
                links = self.link_extractor.extract_links_from_page(
                    page, page_num)
                page_data['links'] = links

            # Extract footnotes
            if self.config.get('extract_footnotes', True):
                footnotes = self.footnote_extractor.extract_footnotes_from_page(
                    page, page_num)
                page_data['footnotes'] = footnotes

            # Process regular text content
            self._process_text_content(page, page_data)

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

    def _process_text_content(self, page, page_data: Dict[str, Any]):
        """Process text content with heading detection and formatting."""
        # Handle multi-column layout
        if self.config.get('handle_multi_column', True):
            multi_column_text = self.text_extractor.handle_multi_column_text(
                page)
            if multi_column_text:
                for text in multi_column_text:
                    text = self.text_extractor.handle_mathematical_content(
                        text)
                    page_data['content'].append(text)
                return

        # Regular text processing
        current_paragraph = []
        blocks = page.get_text("dict")

        for block in blocks.get("blocks", []):
            if "lines" in block:
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
                    # Skip if likely part of already extracted table
                    if (len(page_data.get('tables', [])) > 0 and
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
            page_data['content'].append('\n'.join(current_paragraph))

        # Add footnotes and citations if found
        if page_data.get('footnotes'):
            page_data['content'].append("### Footnotes")
            for footnote in page_data['footnotes']:
                page_data['content'].append(
                    f"{footnote.get('number', '')}. {footnote.get('content', '')}")

        if page_data.get('links', {}).get('citations'):
            page_data['content'].append("### Citations")
            for citation in page_data['links']['citations']:
                page_data['content'].append(f"- {citation.get('text', '')}")

    def _create_final_content(self, metadata: Dict[str, Any],
                              enriched_metadata: Optional[Dict[str, Any]],
                              markdown_content: List[str]) -> str:
        """Create final markdown content with frontmatter and bibliography."""
        final_content = []

        # Add frontmatter if enabled
        if self.config.get('extract_metadata', True) and (metadata or enriched_metadata):
            frontmatter = self.content_processor.create_frontmatter(
                metadata, enriched_metadata)
            final_content.extend(frontmatter)

        # Add main content
        final_content.extend(markdown_content)

        # Add bibliography section if available
        if enriched_metadata and self.config.get('show_bibliography', True):
            bib_section = self.content_processor.create_bibliography_section(
                enriched_metadata)
            if bib_section:
                final_content.append("\n---\n")
                final_content.append(bib_section)

        # Join and post-process
        content = '\n\n'.join(final_content)
        return self.content_processor.post_process_content(content)

    def _save_and_report(self, final_content: str, pdf_path: str, output_path: str,
                         metadata: Dict[str, Any], enriched_metadata: Optional[Dict[str, Any]],
                         page_statistics: Dict[str, Any], doc) -> bool:
        """Save final content and create reports."""
        try:
            # Write markdown file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_content)
            self.logger.info(f"Markdown saved: {output_path}")

            # Create conversion report
            if self.config.get('create_reports', True):
                quality_metrics = validate_conversion_quality(
                    doc, final_content)

                # Add enrichment info
                if enriched_metadata:
                    quality_metrics['enrichment_sources'] = enriched_metadata.get(
                        'enrichment_sources', [])
                    quality_metrics['has_bibliographic_data'] = bool(
                        enriched_metadata.get('bibliographic_data'))

                # Add page statistics
                quality_metrics.update(page_statistics)

                create_conversion_report(
                    pdf_path, metadata, quality_metrics, output_path)

            self.logger.info(
                f"Successfully converted: {pdf_path} -> {output_path}")
            return True

        except UnicodeEncodeError:
            # Fallback for encoding issues
            clean_content = final_content.encode(
                'utf-8', errors='ignore').decode('utf-8')
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(clean_content)
            self.logger.warning(
                "Some characters were removed due to encoding issues")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save conversion results: {e}")
            return False

    def _save_bibtex_entries(self, enriched_metadata: Dict[str, Any],
                             paper_title: str, output_path: str):
        """Save BibTeX entries for the paper."""
        bibtex_entry = self.bib_enricher.generate_bibtex_entry(
            enriched_metadata)
        if bibtex_entry:
            individual_bibtex_path = Path(output_path).with_suffix('.bib')
            with open(individual_bibtex_path, 'w', encoding='utf-8') as f:
                f.write(f"% Individual BibTeX entry for: {paper_title}\n")
                f.write(
                    f"% Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(bibtex_entry)
            self.logger.info(
                f"Individual BibTeX file saved: {individual_bibtex_path}")

        # Save enriched metadata for combined BibTeX generation
        enriched_path = Path(output_path).with_suffix('.enriched.json')
        with open(enriched_path, 'w', encoding='utf-8') as f:
            json.dump(enriched_metadata, f, indent=2, ensure_ascii=False)

    def convert_directory(self, directory_path: str):
        """Convert all PDF files in a directory."""
        directory = Path(directory_path)

        if not directory.exists() or not directory.is_dir():
            self.logger.error(f"Directory not found: {directory_path}")
            return

        pdf_files = list(directory.glob("*.pdf"))
        if not pdf_files:
            self.logger.warning(f"No PDF files found in {directory_path}")
            return

        self.logger.info(
            f"Found {len(pdf_files)} PDF files in {directory_path}")

        success_count = 0
        for pdf_file in pdf_files:
            try:
                if self.convert_pdf_to_markdown(str(pdf_file)):
                    success_count += 1
                else:
                    self.logger.error(f"Failed to convert: {pdf_file}")
            except Exception as e:
                self.logger.error(f"Error converting {pdf_file}: {e}")

        self.logger.info(
            f"Successfully converted {success_count}/{len(pdf_files)} files")

        # Create combined outputs if enabled
        if self.config.get('create_combined_output', True):
            self._create_combined_outputs()

    def _handle_corrupted_or_scanned_pdfs(self, doc) -> bool:
        """Check if PDF is readable or needs special handling."""
        try:
            if len(doc) == 0:
                return False

            # Sample a few pages to check for text content
            sample_pages = min(3, len(doc))
            total_text_length = 0

            for page_num in range(sample_pages):
                sample_page = doc[page_num]
                sample_text = sample_page.get_text()
                total_text_length += len(sample_text.strip())

            # If very little text found, might be scanned
            if total_text_length < 100:
                self.logger.warning(
                    "PDF appears to be scanned or image-based. OCR might be needed.")
                # Don't return False - let OCR handle it
                return True

            return True
        except Exception as e:
            self.logger.error(f"Error checking PDF content: {e}")
            return False

    def _extract_title_from_text(self, text: str) -> str:
        """Extract likely title from text content."""
        lines = text.split('\n')[:10]  # Check first 10 lines

        for line in lines:
            line = line.strip()
            if len(line) > 10 and len(line) < 200:  # Reasonable title length
                # Remove common prefixes
                if not line.lower().startswith(('abstract', 'introduction', 'keywords')):
                    return line

        return "Untitled Document"

    def _create_combined_outputs(self):
        """Create combined markdown and bibliography files."""
        try:
            from .utils import create_combined_markdown, create_combined_bibliography

            out_dir = Path("out")
            create_combined_markdown(out_dir)
            create_combined_bibliography(out_dir)

        except Exception as e:
            self.logger.warning(f"Failed to create combined outputs: {e}")
