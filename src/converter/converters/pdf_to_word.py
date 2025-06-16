"""PDF to Word conversion using multiple strategies."""

import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
import pdf2docx
import tempfile
import shutil


class PDFToWordConverter:
    """Convert PDF files to Word documents with multiple strategies."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)

    def convert(self, pdf_path: str, output_path: Optional[str] = None) -> str:
        """
        Convert PDF to Word document.

        Args:
            pdf_path: Path to input PDF file
            output_path: Path for output Word file (optional)

        Returns:
            Path to converted Word document
        """
        pdf_path = Path(pdf_path)

        if output_path is None:
            output_path = pdf_path.with_suffix('.docx')
        else:
            output_path = Path(output_path)

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Try different conversion strategies
        strategies = [
            self._convert_with_pdf2docx,
            self._convert_with_libreoffice,
        ]

        for strategy in strategies:
            try:
                self.logger.info(
                    f"Trying {strategy.__name__} for {pdf_path.name}")
                result = strategy(str(pdf_path), str(output_path))
                if result and Path(result).exists():
                    self.logger.info(
                        f"Successfully converted using {strategy.__name__}")
                    return str(result)
            except Exception as e:
                self.logger.warning(f"{strategy.__name__} failed: {e}")
                continue

        raise RuntimeError(
            f"All PDF to Word conversion strategies failed for {pdf_path}")

    def _convert_with_pdf2docx(self, pdf_path: str, output_path: str) -> str:
        """Convert using pdf2docx library with enhanced multi-column support."""
        settings = self.config.get('pdf2docx_settings', {})

        # Enhanced settings for better column layout handling
        enhanced_settings = {
            'start_page': settings.get('start_page', 0),
            'end_page': settings.get('end_page', None),
            'image_resolution': settings.get('image_resolution', 150),
            'cpu_count': settings.get('cpu_count', None),
            'password': settings.get('password', None)
        }

        self.logger.info(
            f"Using enhanced pdf2docx settings for multi-column layout")
        self.logger.info(
            f"Image resolution: {enhanced_settings['image_resolution']}")

        # Create converter
        cv = pdf2docx.Converter(pdf_path)

        try:
            # Convert with enhanced settings
            cv.convert(
                output_path,
                **enhanced_settings
            )

            self.logger.info(f"PDF to Word conversion completed successfully")

            # Validate output file
            output_file = Path(output_path)
            if output_file.exists():
                file_size = output_file.stat().st_size
                self.logger.info(
                    f"Generated Word file size: {file_size:,} bytes")
            else:
                raise RuntimeError("Output file was not created")

        except Exception as e:
            self.logger.error(f"pdf2docx conversion failed: {e}")
            raise
        finally:
            cv.close()

        return output_path

    def _convert_with_libreoffice(self, pdf_path: str, output_path: str) -> str:
        """Convert using LibreOffice command line."""
        try:
            # Create temporary directory for LibreOffice conversion
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_dir = Path(temp_dir)

                # Run LibreOffice conversion
                cmd = [
                    'libreoffice',
                    '--headless',
                    '--convert-to', 'docx',
                    '--outdir', str(temp_dir),
                    str(pdf_path)
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minutes timeout
                )

                if result.returncode != 0:
                    raise RuntimeError(
                        f"LibreOffice conversion failed: {result.stderr}")

                # Find generated file and move to desired location
                pdf_name = Path(pdf_path).stem
                generated_file = temp_dir / f"{pdf_name}.docx"

                if generated_file.exists():
                    shutil.move(str(generated_file), output_path)
                    return output_path
                else:
                    raise RuntimeError(
                        "LibreOffice did not generate expected output file")

        except subprocess.TimeoutExpired:
            raise RuntimeError("LibreOffice conversion timed out")
        except FileNotFoundError:
            raise RuntimeError(
                "LibreOffice not found. Please install LibreOffice.")

    def is_libreoffice_available(self) -> bool:
        """Check if LibreOffice is available."""
        try:
            subprocess.run(['libreoffice', '--version'],
                           capture_output=True, timeout=10)
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
