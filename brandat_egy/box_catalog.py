
from django.db.models import Prefetch
from django.utils import timezone

from .models import Box, BoxImage, BoxItem, DailyOffer


def get_box_catalog_queryset(*, at=None):
    at = timezone.now() if at is None else at

    active_offers = DailyOffer.objects.filter(
        is_active=True,
        starts_at__lte=at,
        ends_at__gt=at,
    ).order_by("price", "pk")

    box_items = (
        BoxItem.objects
        .select_related("variant__product")
        .order_by("pk")
    )

    return (
        Box.objects.filter(is_active=True)
        .prefetch_related(
            Prefetch(
                "images",
                queryset=BoxImage.objects.order_by(
                    "-is_main", "pk"
                ),
                to_attr="catalog_images",
            ),
            Prefetch(
                "items",
                queryset=box_items,
                to_attr="catalog_items",
            ),
            Prefetch(
                "daily_offers",
                queryset=active_offers,
                to_attr="catalog_active_offers",
            ),
        )
        .order_by("-created_at", "-pk")
    )


def get_box_catalog_price(box):
    base_price = (
        box.discount_price
        if box.discount_price is not None
        else box.price
    )

    offers = box.catalog_active_offers

    if offers:
        return min(base_price, offers[0].price)

    return base_price


def get_box_catalog_stock(box):
    if not box.is_active or box.stock <= 0:
        return 0

    items = box.catalog_items

    if not items:
        return 0

    available = box.stock

    for item in items:
        variant = item.variant

        if not variant.can_purchase:
            return 0

        possible_boxes = variant.stock // item.quantity

        available = min(
            available,
            possible_boxes,
        )

    return available
