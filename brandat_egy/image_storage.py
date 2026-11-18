
import logging

from .models import ProductImage ,ProductImage, BoxImage


logger = logging.getLogger(__name__)




from .models import ProductImage, BoxImage


def delete_unused_image_file(*, filename, storage):
    if not filename:
        return

    if ProductImage.objects.filter(
        image=filename
    ).exists():
        return

    if BoxImage.objects.filter(
        image=filename
    ).exists():
        return

    try:
        storage.delete(filename)
    except Exception:
        logger.exception(
            "Failed to delete image file: %s",
            filename,
        )

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


def delete_unused_box_image_file(*, filename, storage):
    if not filename:
        return

    if BoxImage.objects.filter(
        image=filename
    ).exists():
        return

    try:
        storage.delete(filename)
    except Exception:
        logger.exception(
            "Failed to delete box image file: %s",
            filename,
        )
