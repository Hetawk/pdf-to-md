"""Basic image extraction functionality for PDF processing."""

import fitz
from pathlib import Path
from typing import List

from ..base import BaseExtractor


class ImageExtractor(BaseExtractor):
    """Extract images from PDF pages."""

    def extract_images(self, doc, output_dir: Path) -> List[str]:
        """Extract all images from the PDF document."""
        if not self.config.get('extract_images', True):
            return []

        images_dir = output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        image_refs = []
        image_count = 0

        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images()

            for img_index, img in enumerate(image_list):
                try:
                    # Get image data
                    xref = img[0]
                    pix = fitz.Pixmap(doc, xref)

                    # Skip images that are too small (likely artifacts)
                    if pix.width < 50 or pix.height < 50:
                        pix = None
                        continue

                    # Generate filename
                    image_filename = f"image_{page_num+1}_{img_index+1}.png"
                    image_path = images_dir / image_filename

                    # Save image
                    if pix.n - pix.alpha < 4:  # GRAY or RGB
                        pix.save(str(image_path))
                    else:  # CMYK: convert to RGB first
                        pix1 = fitz.Pixmap(fitz.csRGB, pix)
                        pix1.save(str(image_path))
                        pix1 = None

                    # Store relative path for markdown
                    relative_path = f"images/{image_filename}"
                    image_refs.append(relative_path)
                    image_count += 1

                    self.logger.debug(f"Extracted image: {image_filename}")
                    pix = None

                except Exception as e:
                    self.logger.warning(
                        f"Failed to extract image {img_index} from page {page_num}: {e}")
                    continue

        self.logger.info(f"Extracted {image_count} images")
        return image_refs
