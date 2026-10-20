
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone

from .cart import Cart
from .models import (
    Box,
    BoxItem,
    DailyOffer,
    Product,
    ProductVariant,
)
from .pricing import get_effective_price
from .services import create_order_from_cart


class DailyOfferPricingTests(TestCase):

    def setUp(self):
        self.now = timezone.now()

        self.product = Product.objects.create(
            name_ar="سيرم للشعر",
            description_ar="سيرم للعناية بالشعر",
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku="SERUM-001",
            price=Decimal("300.00"),
            discount_price=Decimal("270.00"),
            stock=10,
        )

        self.box = Box.objects.create(
            name_ar="بوكس العناية",
            description_ar="بوكس منتجات العناية",
            sku="BOX-001",
            price=Decimal("500.00"),
            stock=5,
        )

        BoxItem.objects.create(
            box=self.box,
            variant=self.variant,
            quantity=1,
        )

    def create_offer(
        self,
        *,
        for_box=False,
        price="220.00",
        starts_at=None,
        ends_at=None,
        is_active=True,
    ):
        target = (
            {"box": self.box}
            if for_box
            else {"variant": self.variant}
        )

        return DailyOffer.objects.create(
            **target,
            price=Decimal(price),
            starts_at=(
                starts_at
                if starts_at is not None
                else self.now - timedelta(hours=1)
            ),
            ends_at=(
                ends_at
                if ends_at is not None
                else self.now + timedelta(hours=1)
            ),
            is_active=is_active,
        )

    def test_no_offer_uses_discount_price(self):
        self.assertEqual(
            self.variant.final_price,
            Decimal("270.00"),
        )

    def test_active_variant_offer(self):
        self.create_offer()

        self.assertEqual(
            self.variant.final_price,
            Decimal("220.00"),
        )

    def test_inactive_offer_is_ignored(self):
        self.create_offer(is_active=False)

        self.assertEqual(
            self.variant.final_price,
            Decimal("270.00"),
        )

    def test_offer_time_boundaries(self):
        starts = self.now
        ends = self.now + timedelta(hours=1)

        self.create_offer(
            starts_at=starts,
            ends_at=ends,
        )

        self.assertEqual(
            get_effective_price(
                self.variant,
                at=starts - timedelta(seconds=1),
            ),
            Decimal("270.00"),
        )

        self.assertEqual(
            get_effective_price(self.variant, at=starts),
            Decimal("220.00"),
        )

        self.assertEqual(
            get_effective_price(self.variant, at=ends),
            Decimal("270.00"),
        )

    def test_lowest_price_wins(self):
        self.create_offer(price="280.00")

        self.assertEqual(
            self.variant.final_price,
            Decimal("270.00"),
        )

    def test_box_offer(self):
        self.create_offer(
            for_box=True,
            price="400.00",
        )

        self.assertEqual(
            self.box.final_price,
            Decimal("400.00"),
        )

    def test_checkout_saves_offer_price(self):
        self.create_offer(price="220.00")

        self.create_offer(
            for_box=True,
            price="400.00",
        )

        request = SimpleNamespace(
            session=self.client.session,
        )
        cart = Cart(request)

        cart.add(self.variant, quantity=2)
        cart.add(self.box, quantity=1)

        self.assertEqual(
            cart.get_total_price(),
            Decimal("840.00"),
        )

        order = create_order_from_cart(
            cart=cart,
            customer_name="Test Customer",
            phone="01000000000",
            address="Cairo",
        )

        self.assertEqual(
            order.items.get().price,
            Decimal("220.00"),
        )

        self.assertEqual(
            order.boxes.get().price,
            Decimal("400.00"),
        )

        self.assertEqual(
            order.total_price,
            Decimal("840.00"),
        )

        # Ending offers cannot change a past order.
        DailyOffer.objects.update(is_active=False)

        self.assertEqual(
            order.total_price,
            Decimal("840.00"),
        )
