
from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APITestCase

from .models import (
    Brand,
    Category,
    DailyOffer,
    Product,
    ProductVariant,
)


class ProductCatalogFilterTests(APITestCase):

    def setUp(self):
        self.url = reverse("product-list")

        self.cosrx = Brand.objects.create(
            name_ar="كوسركس",
            name_en="COSRX",
            slug="cosrx",
        )

        self.anua = Brand.objects.create(
            name_ar="أنوا",
            name_en="ANUA",
            slug="anua",
        )

        self.skincare = Category.objects.create(
            name_ar="العناية بالبشرة",
            name_en="Skincare",
            slug="skincare",
        )

        self.serums = Category.objects.create(
            name_ar="السيروم",
            name_en="Serums",
            slug="serums",
            parent=self.skincare,
        )

        self.moisturizers = Category.objects.create(
            name_ar="المرطبات",
            name_en="Moisturizers",
            slug="moisturizers",
            parent=self.skincare,
        )

        self.haircare = Category.objects.create(
            name_ar="العناية بالشعر",
            name_en="Haircare",
            slug="haircare",
        )

        self.serum, self.serum_variant = (
            self.create_product(
                "Serum", "SERUM",
                self.cosrx, self.serums,
                "350.00", 5,
            )
        )

        self.lotion, self.lotion_variant = (
            self.create_product(
                "Lotion", "LOTION",
                self.anua, self.moisturizers,
                "600.00", 3,
            )
        )

        self.toner, self.toner_variant = (
            self.create_product(
                "Toner", "TONER",
                self.cosrx, self.skincare,
                "200.00", 0,
            )
        )

        self.shampoo, self.shampoo_variant = (
            self.create_product(
                "Shampoo", "SHAMPOO",
                self.anua, self.haircare,
                "100.00", 4,
            )
        )

    def create_product(
        self, name, sku, brand, category, price, stock
    ):
        product = Product.objects.create(
            name_ar=name,
            name_en=name,
            description_ar="منتج تجريبي",
            brand=brand,
            category=category,
        )

        variant = ProductVariant.objects.create(
            product=product,
            sku=sku,
            price=Decimal(price),
            stock=stock,
        )

        return product, variant

    def get_ids(self, response):
        return [
            item["id"]
            for item in response.data["results"]
        ]

    def test_filter_by_single_brand(self):
        response = self.client.get(
            self.url,
            {"brand": "cosrx"},
        )

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            set(self.get_ids(response)),
            {self.serum.pk, self.toner.pk},
        )

    def test_filter_by_multiple_brands(self):
        response = self.client.get(
            self.url,
            {"brand": "cosrx,anua"},
        )

        self.assertEqual(response.data["count"], 4)

    def test_parent_category_includes_children(self):
        response = self.client.get(
            self.url,
            {"category": "skincare"},
        )

        self.assertEqual(
            set(self.get_ids(response)),
            {
                self.serum.pk,
                self.lotion.pk,
                self.toner.pk,
            },
        )

    def test_child_category_filter(self):
        response = self.client.get(
            self.url,
            {"category": "serums"},
        )

        self.assertEqual(
            self.get_ids(response),
            [self.serum.pk],
        )

    def test_price_range_uses_starting_price(self):
        response = self.client.get(
            self.url,
            {
                "min_price": "300",
                "max_price": "650",
            },
        )

        self.assertEqual(
            set(self.get_ids(response)),
            {self.serum.pk, self.lotion.pk},
        )

    def test_available_only(self):
        response = self.client.get(
            self.url,
            {"available_only": "true"},
        )

        self.assertEqual(response.data["count"], 3)

        self.assertNotIn(
            self.toner.pk,
            self.get_ids(response),
        )

    def test_price_sort_ascending(self):
        response = self.client.get(
            self.url,
            {"ordering": "price_asc"},
        )

        self.assertEqual(
            self.get_ids(response),
            [
                self.shampoo.pk,
                self.serum.pk,
                self.lotion.pk,
                self.toner.pk,
            ],
        )

    def test_price_sort_descending(self):
        response = self.client.get(
            self.url,
            {"ordering": "price_desc"},
        )

        self.assertEqual(
            self.get_ids(response),
            [
                self.lotion.pk,
                self.serum.pk,
                self.shampoo.pk,
                self.toner.pk,
            ],
        )

    def test_combined_filters(self):
        response = self.client.get(
            self.url,
            {
                "brand": "cosrx",
                "category": "skincare",
                "min_price": "300",
                "max_price": "400",
                "available_only": "true",
                "ordering": "price_asc",
            },
        )

        self.assertEqual(
            self.get_ids(response),
            [self.serum.pk],
        )

    def test_daily_offer_affects_price_filter(self):
        now = timezone.now()

        DailyOffer.objects.create(
            variant=self.lotion_variant,
            price=Decimal("250.00"),
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=1),
            is_active=True,
        )

        response = self.client.get(
            self.url,
            {
                "max_price": "300",
                "available_only": "true",
            },
        )

        self.assertEqual(
            set(self.get_ids(response)),
            {self.lotion.pk, self.shampoo.pk},
        )

    def test_invalid_filters_return_400(self):
        invalid_queries = [
            {
                "min_price": "1000",
                "max_price": "200",
            },
            {"min_price": "-50"},
            {"ordering": "invalid"},
            {"available_only": "maybe"},
        ]

        for params in invalid_queries:
            with self.subTest(params=params):
                response = self.client.get(
                    self.url,
                    params,
                )

                self.assertEqual(
                    response.status_code,
                    400,
                )

    def test_pagination_after_filtering(self):
        first = self.client.get(
            self.url,
            {
                "category": "skincare",
                "page_size": 1,
                "page": 1,
            },
        )

        second = self.client.get(
            self.url,
            {
                "category": "skincare",
                "page_size": 1,
                "page": 2,
            },
        )

        self.assertEqual(first.data["count"], 3)
        self.assertEqual(second.data["count"], 3)

        self.assertNotEqual(
            self.get_ids(first),
            self.get_ids(second),
        )
