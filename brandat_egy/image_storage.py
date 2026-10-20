
import logging

from .models import ProductImage


logger = logging.getLogger(__name__)


def delete_unused_product_image_file(
    *,
    filename,
    storage,
):
    if not filename:
        return

    # Another image record may still use this file.
    if ProductImage.objects.filter(
        image=filename
    ).exists():
        return

    try:
        storage.delete(filename)
    except Exception:
        logger.exception(
            "Failed to delete product image file: %s",
            filename,
        )
