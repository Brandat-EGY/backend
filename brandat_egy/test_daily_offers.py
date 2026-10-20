
from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APITestCase

from .models import (
    Box,
    BoxItem,
    DailyOffer,
    Product,
    ProductVariant,
)


class DailyOfferListTests(APITestCase):

    def setUp(self):
        self.url = reverse("daily-offer-list")

        self.product = Product.objects.create(
            name_ar="سيروم مرطب",
            name_en="Hydrating Serum",
            description_ar="سيروم للعناية بالبشرة",
            is_available=True,
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            price=Decimal("200.00"),
            discount_price=Decimal("180.00"),
            stock=5,
            is_active=True,
        )

        self.box = Box.objects.create(
            name_ar="بوكس الترطيب",
            name_en="Hydration Box",
            description_ar="بوكس العناية بالبشرة",
            sku="BOX-OFFER-001",
            price=Decimal("900.00"),
            discount_price=Decimal("800.00"),
            stock=10,
            is_active=True,
        )

        BoxItem.objects.create(
            box=self.box,
            variant=self.variant,
            quantity=2,
        )

        now = timezone.now()

        self.product_offer = DailyOffer.objects.create(
            variant=self.variant,
            price=Decimal("150.00"),
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=2),
            is_active=True,
        )

        self.box_offer = DailyOffer.objects.create(
            box=self.box,
            price=Decimal("700.00"),
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=2),
            is_active=True,
        )

    def test_guest_can_view_current_offers(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)

        types = {
            item["target_type"]
            for item in response.data["results"]
        }

        self.assertEqual(
            types,
            {"product_variant", "box"},
        )

    def test_offer_prices_are_correct(self):
        response = self.client.get(self.url)

        offers = {
            item["target_type"]: item
            for item in response.data["results"]
        }

        product_offer = offers["product_variant"]
        box_offer = offers["box"]

        self.assertEqual(
            product_offer["price_before_offer"],
            "180.00",
        )
        self.assertEqual(
            product_offer["final_price"],
            "150.00",
        )

        self.assertEqual(
            box_offer["price_before_offer"],
            "800.00",
        )
        self.assertEqual(
            box_offer["final_price"],
            "700.00",
        )

    def test_inactive_offers_are_hidden(self):
        self.product_offer.is_active = False
        self.product_offer.save(
            update_fields=["is_active"]
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_future_offer_is_hidden(self):
        now = timezone.now()

        self.product_offer.starts_at = (
            now + timedelta(days=1)
        )
        self.product_offer.ends_at = (
            now + timedelta(days=2)
        )
        self.product_offer.save(
            update_fields=["starts_at", "ends_at"]
        )

        response = self.client.get(self.url)

        self.assertEqual(response.data["count"], 1)

    def test_expired_offer_is_hidden(self):
        now = timezone.now()

        self.product_offer.starts_at = (
            now - timedelta(days=2)
        )
        self.product_offer.ends_at = (
            now - timedelta(days=1)
        )
        self.product_offer.save(
            update_fields=["starts_at", "ends_at"]
        )

        response = self.client.get(self.url)

        self.assertEqual(response.data["count"], 1)

    def test_unpublished_product_offer_is_hidden(self):
        self.product.is_available = False
        self.product.save(
            update_fields=["is_available"]
        )

        response = self.client.get(self.url)

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["target_type"],
            "box",
        )

    def test_out_of_stock_offer_remains_visible(self):
        self.variant.stock = 0
        self.variant.save(update_fields=["stock"])

        response = self.client.get(self.url)

        self.assertEqual(response.data["count"], 2)

        for offer in response.data["results"]:
            self.assertEqual(offer["available_stock"], 0)
            self.assertFalse(offer["in_stock"])
