"""Hybrid PDF to Markdown converter using PDF → Word → Markdown pipeline."""

import logging
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from .pdf_to_word import PDFToWordConverter
from .word_processor import WordDocumentProcessor
from .word_to_markdown import WordToMarkdownConverter


class HybridPDFConverter:
    """
    Hybrid converter that uses PDF → Word → Markdown pipeline for better
    format preservation, especially for academic papers with complex layouts.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Initialize converters
        self.pdf_to_word = PDFToWordConverter(config)
        self.word_processor = WordDocumentProcessor(config)
        self.word_to_md = WordToMarkdownConverter(config)

    def convert(self, pdf_path: str, output_path: Optional[str] = None,
                cleanup_intermediate: bool = True) -> Tuple[str, Dict[str, Any]]:
        """
        Convert PDF to Markdown using the hybrid pipeline.

        Args:
            pdf_path: Path to input PDF file
            output_path: Path for output Markdown file (optional)
            cleanup_intermediate: Whether to clean up intermediate Word file

        Returns:
            Tuple of (markdown_path, conversion_report)
        """
        pdf_path = Path(pdf_path)

        if output_path is None:
            output_path = pdf_path.with_suffix('.md')
        else:
            output_path = Path(output_path)

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        conversion_report = {
            'input_file': str(pdf_path),
            'output_file': str(output_path),
            'conversion_method': 'hybrid_pdf_word_markdown',
            'steps_completed': [],
            'errors': [],
            'warnings': [],
            'intermediate_files': []
        }

        try:
            # Step 1: Convert PDF to Word
            self.logger.info(
                f"Step 1: Converting PDF to Word: {pdf_path.name}")
            word_path = self._get_intermediate_word_path(pdf_path, output_path)

            try:
                word_result = self.pdf_to_word.convert(
                    str(pdf_path), str(word_path))
                conversion_report['steps_completed'].append('pdf_to_word')
                conversion_report['intermediate_files'].append(word_result)
                self.logger.info(
                    f"PDF to Word conversion completed: {word_result}")
            except Exception as e:
                error_msg = f"PDF to Word conversion failed: {e}"
                conversion_report['errors'].append(error_msg)
                raise RuntimeError(error_msg)

            # Step 2: Process Word document (optional analysis)
            if self.config.get('analyze_word_structure', False):
                self.logger.info(f"Step 2: Analyzing Word document structure")
                try:
                    word_analysis = self.word_processor.process_document(
                        word_result)
                    conversion_report['word_analysis'] = word_analysis
                    conversion_report['steps_completed'].append(
                        'word_analysis')
                    self.logger.info("Word document analysis completed")
                except Exception as e:
                    warning_msg = f"Word analysis failed (non-critical): {e}"
                    conversion_report['warnings'].append(warning_msg)
                    self.logger.warning(warning_msg)

            # Step 3: Convert Word to Markdown
            self.logger.info(f"Step 3: Converting Word to Markdown")
            try:
                md_result = self.word_to_md.convert(
                    word_result, str(output_path))
                conversion_report['steps_completed'].append('word_to_markdown')
                self.logger.info(
                    f"Word to Markdown conversion completed: {md_result}")
            except Exception as e:
                error_msg = f"Word to Markdown conversion failed: {e}"
                conversion_report['errors'].append(error_msg)
                raise RuntimeError(error_msg)

            # Step 4: Post-process and validate
            self.logger.info(f"Step 4: Post-processing Markdown")
            try:
                self._post_process_markdown(output_path, conversion_report)
                conversion_report['steps_completed'].append('post_processing')
            except Exception as e:
                warning_msg = f"Post-processing failed (non-critical): {e}"
                conversion_report['warnings'].append(warning_msg)
                self.logger.warning(warning_msg)

            # Step 5: Apply bibliographic enrichment
            self.logger.info(f"Step 5: Applying bibliographic enrichment")
            try:
                self._apply_bibliographic_enrichment(output_path, pdf_path)
                conversion_report['steps_completed'].append(
                    'bibliographic_enrichment')
            except Exception as e:
                warning_msg = f"Bibliographic enrichment failed (non-critical): {e}"
                conversion_report['warnings'].append(warning_msg)
                self.logger.warning(warning_msg)

            # Step 6: Cleanup intermediate files if requested
            if cleanup_intermediate and Path(word_result).exists():
                try:
                    Path(word_result).unlink()
                    conversion_report['intermediate_files_cleaned'] = True
                    self.logger.info("Intermediate Word file cleaned up")
                except Exception as e:
                    warning_msg = f"Cleanup failed: {e}"
                    conversion_report['warnings'].append(warning_msg)
                    self.logger.warning(warning_msg)

            conversion_report['success'] = True
            conversion_report['final_output'] = str(output_path)

            return str(output_path), conversion_report

        except Exception as e:
            conversion_report['success'] = False
            conversion_report['final_error'] = str(e)
            self.logger.error(f"Hybrid conversion failed: {e}")
            raise

    def _get_intermediate_word_path(self, pdf_path: Path, output_path: Path) -> Path:
        """Generate path for intermediate Word file."""
        # Get the base output directory from the markdown file path
        # If output_path is like: out/md-json/filename.md
        # We want word files in: out/md-json/word/filename_intermediate.docx

        base_output_dir = output_path.parent  # This should be out/md-json

        # Create word subdirectory in the same location as the markdown output
        word_dir = base_output_dir / 'word'
        word_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"Word files will be saved to: {word_dir}")

        word_filename = pdf_path.stem + '_intermediate.docx'
        return word_dir / word_filename

    def _post_process_markdown(self, markdown_path: Path, report: Dict[str, Any]):
        """Post-process the generated markdown file."""
        try:
            with open(markdown_path, 'r', encoding='utf-8') as f:
                content = f.read()

            original_length = len(content)

            # Apply post-processing improvements
            content = self._improve_markdown_formatting(content)
            content = self._fix_academic_paper_issues(content)

            # Write back improved content
            with open(markdown_path, 'w', encoding='utf-8') as f:
                f.write(content)

            # Add metrics to report
            report['post_processing'] = {
                'original_length': original_length,
                'final_length': len(content),
                'improvement_applied': True
            }

        except Exception as e:
            self.logger.warning(f"Post-processing markdown failed: {e}")
            raise

    def _improve_markdown_formatting(self, content: str) -> str:
        """Apply general markdown formatting improvements."""
        import re

        lines = content.split('\n')
        improved_lines = []

        prev_line = ""
        for i, line in enumerate(lines):
            line = line.rstrip()

            # Fix heading spacing
            if line.startswith('#') and prev_line.strip() != "":
                improved_lines.append("")

            # Fix list formatting
            if (line.strip().startswith(('- ', '* ', '+ ')) or
                    re.match(r'^\d+\. ', line.strip())):
                if (prev_line.strip() != "" and
                    not prev_line.strip().startswith(('- ', '* ', '+ ')) and
                        not re.match(r'^\d+\. ', prev_line.strip())):
                    improved_lines.append("")

            improved_lines.append(line)
            prev_line = line

        return '\n'.join(improved_lines)

    def _fix_academic_paper_issues(self, content: str) -> str:
        """Fix common issues in academic paper conversions, especially multi-column layouts."""
        import re

        self.logger.info("Applying academic paper formatting fixes")

        # Enhanced fixes for multi-column layouts and academic papers
        fixes = [
            # Fix broken references
            (r'\[\s*(\d+)\s*\]', r'[\1]'),
            # Fix spaced out citations
            (r'\(\s*([^)]+)\s*\)', r'(\1)'),
            # Fix table formatting issues
            (r'\|\s*\|\s*\|', r'| |'),
            # Fix equation spacing
            (r'^\s*\$\s*(.+)\s*\$\s*$', r'$$\1$$'),
            # Fix multi-column text flow issues - merge broken lines
            (r'(\w+)-\s*\n\s*(\w+)', r'\1\2'),
            # Fix scattered single characters (common in column parsing)
            (r'\n\s*([a-zA-Z])\s*\n', r' \1 '),
            # Fix broken section headers
            (r'\n([A-Z][A-Z\s]{2,})\n', r'\n\n## \1\n\n'),
            # Fix broken figure/table references
            (r'Figure\s*(\d+)', r'Figure \1'),
            (r'Table\s*(\d+)', r'Table \1'),
            # Fix mathematical symbols that got separated
            (r'(\w+)\s*=\s*(\w+)', r'\1 = \2'),
        ]

        original_length = len(content)

        for i, (pattern, replacement) in enumerate(fixes):
            try:
                before_length = len(content)
                content = re.sub(pattern, replacement,
                                 content, flags=re.MULTILINE)
                after_length = len(content)

                if before_length != after_length:
                    self.logger.debug(
                        f"Applied fix {i+1}: {before_length} -> {after_length} chars")

            except Exception as e:
                self.logger.warning(f"Fix {i+1} failed: {e}")
                continue

        # Additional multi-column specific fixes
        content = self._fix_multi_column_text_flow(content)

        final_length = len(content)
        self.logger.info(
            f"Academic fixes applied: {original_length} -> {final_length} characters")

        return content

    def _fix_multi_column_text_flow(self, content: str) -> str:
        """Fix text flow issues specific to multi-column layouts."""
        import re

        lines = content.split('\n')
        fixed_lines = []

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Skip empty lines
            if not line:
                fixed_lines.append('')
                i += 1
                continue

            # Check for orphaned short lines that might be column artifacts
            if (len(line) < 10 and
                i > 0 and i < len(lines) - 1 and
                not line.startswith('#') and
                not line.startswith('*') and
                not line.startswith('-') and
                    not re.match(r'^\d+\.', line)):

                # Try to merge with previous or next line
                if (fixed_lines and
                    fixed_lines[-1] and
                    not fixed_lines[-1].endswith('.') and
                        not fixed_lines[-1].endswith('!')):

                    # Merge with previous line
                    fixed_lines[-1] += ' ' + line
                    i += 1
                    continue

            fixed_lines.append(line)
            i += 1

        return '\n'.join(fixed_lines)

    def can_convert(self, pdf_path: str) -> bool:
        """Check if the hybrid converter can handle the given PDF."""
        try:
            # Check if PDF to Word converter is available
            if not hasattr(self.pdf_to_word, 'convert'):
                return False

            # Check if Word to Markdown converter is available
            if not hasattr(self.word_to_md, 'convert'):
                return False

            # Check file exists and is readable
            pdf_path = Path(pdf_path)
            if not pdf_path.exists() or not pdf_path.is_file():
                return False

            return True

        except Exception:
            return False

    def get_conversion_info(self) -> Dict[str, Any]:
        """Get information about the hybrid conversion capabilities."""
        info = {
            'converter_type': 'hybrid_pdf_word_markdown',
            'steps': ['pdf_to_word', 'word_to_markdown', 'post_processing', 'bibliographic_enrichment'],
            'advantages': [
                'Better table preservation',
                'Superior layout handling',
                'Enhanced formatting retention',
                'Academic paper optimized',
                'Bibliographic enrichment'
            ],
            'disadvantages': [
                'Slower conversion',
                'Requires more disk space',
                'More complex error handling'
            ]
        }

        # Add component availability info
        try:
            info['pdf_to_word_available'] = self.pdf_to_word.can_convert('')
        except:
            info['pdf_to_word_available'] = False

        try:
            info['word_to_markdown_available'] = self.word_to_md.can_convert(
                '')
        except:
            info['word_to_markdown_available'] = False

        return info

    def _apply_bibliographic_enrichment(self, markdown_path: Path, pdf_path: Path):
        """Apply bibliographic enrichment to the converted markdown."""
        try:
            # Import enricher here to avoid circular imports
            from ...enricher.metadata_enricher import MetadataEnricher

            enricher = MetadataEnricher(self.config)

            # Extract metadata from PDF and enrich
            metadata = enricher.extract_metadata(str(pdf_path))
            enriched_metadata = enricher.enrich_metadata(metadata)

            # Save enriched metadata
            metadata_path = markdown_path.with_suffix('.enriched.json')
            enricher.save_enriched_metadata(
                enriched_metadata, str(metadata_path))

            # Generate and save BibTeX if enabled
            if self.config.get('generate_bibtex', True):
                bibtex_path = markdown_path.with_suffix('.bib')
                enricher.generate_bibtex(enriched_metadata, str(bibtex_path))

            self.logger.info(
                f"Bibliographic enrichment completed for {markdown_path}")

        except Exception as e:
            self.logger.warning(f"Bibliographic enrichment failed: {e}")
