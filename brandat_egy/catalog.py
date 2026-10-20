
from django.db.models import (
    DecimalField,
    Exists,
    F,
    OuterRef,
    Subquery,
)
from django.db.models.functions import Coalesce, Least
from django.utils import timezone

from .models import DailyOffer, Product, ProductVariant


def get_catalog_queryset(*, at=None, available_only=False, include_unavailable=False):
    at = timezone.now() if at is None else at

    price_field = DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    # Active daily offers for each variant.
    active_offers = (
        DailyOffer.objects.filter(
            variant_id=OuterRef("pk"),
            is_active=True,
            starts_at__lte=at,
            ends_at__gt=at,
        )
        .order_by("price", "pk")
        .values("price")[:1]
    )

    # Variants that can actually be purchased.
    available_variants = ProductVariant.objects.filter(
        product_id=OuterRef("pk"),
        is_active=True,
        stock__gt=0,
    )

    # Calculate the lowest effective variant price.
    cheapest_variant = (
        available_variants
        .annotate(
            base_price=Coalesce(
                "discount_price",
                "price",
                output_field=price_field,
            ),
            offer_price=Subquery(
                active_offers,
                output_field=price_field,
            ),
        )
        .annotate(
            effective_price=Least(
                F("base_price"),
                Coalesce(
                    F("offer_price"),
                    F("base_price"),
                    output_field=price_field,
                ),
                output_field=price_field,
            ),
        )
        .order_by("effective_price", "pk")
        .values("effective_price")[:1]
    )
    
    queryset = Product.objects.all()
    if not include_unavailable:
        queryset = queryset.filter(
            is_available=True
        )

    queryset = (
        queryset
        .select_related("brand", "category")
        .annotate(
            starting_price=Subquery(
                cheapest_variant,
                output_field=price_field,
            ),
            in_stock=Exists(available_variants),
        )
    )


    if available_only:
        queryset = queryset.filter(in_stock=True)

    return queryset
