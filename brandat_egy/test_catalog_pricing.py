
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from .catalog import get_catalog_queryset
from .models import DailyOffer, Product, ProductVariant


class CatalogPricingTests(TestCase):

    def setUp(self):
        self.now = timezone.now()

        self.product = Product.objects.create(
            name_ar="سيرم للبشرة",
            name_en="Face Serum",
            description_ar="سيرم للعناية بالبشرة",
        )

        self.small_variant = ProductVariant.objects.create(
            product=self.product,
            sku="SERUM-30ML",
            size="30ml",
            price=Decimal("250.00"),
            stock=0,
        )

        self.medium_variant = ProductVariant.objects.create(
            product=self.product,
            sku="SERUM-50ML",
            size="50ml",
            price=Decimal("500.00"),
            discount_price=Decimal("450.00"),
            stock=5,
        )

        DailyOffer.objects.create(
            variant=self.medium_variant,
            price=Decimal("380.00"),
            starts_at=self.now - timedelta(hours=1),
            ends_at=self.now + timedelta(hours=1),
            is_active=True,
        )

    def test_lowest_available_effective_price(self):
        product = get_catalog_queryset(
            at=self.now
        ).get(pk=self.product.pk)

        self.assertEqual(
            product.starting_price,
            Decimal("380.00"),
        )

        self.assertTrue(product.in_stock)

    def test_out_of_stock_product_stays_visible(self):
        self.medium_variant.stock = 0
        self.medium_variant.save(update_fields=["stock"])

        product = get_catalog_queryset(
            at=self.now
        ).get(pk=self.product.pk)

        self.assertFalse(product.in_stock)
        self.assertIsNone(product.starting_price)

    def test_available_only_excludes_out_of_stock(self):
        self.medium_variant.stock = 0
        self.medium_variant.save(update_fields=["stock"])

        self.assertFalse(
            get_catalog_queryset(
                at=self.now,
                available_only=True,
            ).filter(pk=self.product.pk).exists()
        )

    def test_expired_offer_is_ignored(self):
        future_time = self.now + timedelta(hours=2)

        product = get_catalog_queryset(
            at=future_time
        ).get(pk=self.product.pk)

        self.assertEqual(
            product.starting_price,
            Decimal("450.00"),
        )

    def test_unavailable_product_is_hidden(self):
        self.product.is_available = False
        self.product.save(update_fields=["is_available"])

        self.assertFalse(
            get_catalog_queryset(
                at=self.now
            ).filter(pk=self.product.pk).exists()
        )
