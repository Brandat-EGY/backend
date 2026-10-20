
from django.utils import timezone


def get_effective_price(item, *, at=None):
    base_price = (
        item.discount_price
        if item.discount_price is not None
        else item.price
    )

    if item.pk is None:
        return base_price

    at = timezone.now() if at is None else at
    

    offer_price = (
        item.daily_offers.filter(
            is_active=True,
            starts_at__lte=at,
            ends_at__gt=at,
        )
        .order_by("price", "pk")
        .values_list("price", flat=True)
        .first()
    )

    if offer_price is None:
        return base_price

    return min(base_price, offer_price)
