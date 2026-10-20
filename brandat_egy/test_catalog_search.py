
from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from .models import Brand, Product, ProductVariant


class ProductCatalogSearchTests(APITestCase):

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

        self.serum = Product.objects.create(
            name_ar="سيروم مرطب",
            name_en="Hydrating Serum",
            description_ar="سيروم للبشرة",
            brand=self.cosrx,
        )

        self.cleanser = Product.objects.create(
            name_ar="غسول الوجه",
            name_en="Face Cleanser",
            description_ar="غسول للبشرة",
            brand=self.cosrx,
        )

        self.hair_serum = Product.objects.create(
            name_ar="سيروم للشعر",
            name_en="Serum",
            description_ar="منتج للشعر",
            brand=self.anua,
        )

        for product, sku, price in (
            (self.serum, "COSRX-30ML", "200.00"),
            (self.cleanser, "COSRX-CLEANSER", "150.00"),
            (self.hair_serum, "ANUA-HAIR", "450.00"),
        ):
            ProductVariant.objects.create(
                product=product,
                sku=sku,
                price=Decimal(price),
                stock=5,
            )

    def get_ids(self, response):
        return [
            item["id"]
            for item in response.data["results"]
        ]

    def test_search_english(self):
        response = self.client.get(
            self.url,
            {"search": "cosrx serum"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.get_ids(response),
            [self.serum.pk],
        )

    def test_search_arabic(self):
        response = self.client.get(
            self.url,
            {"search": "كوسركس سيروم"},
        )

        self.assertEqual(
            self.get_ids(response),
            [self.serum.pk],
        )

    def test_search_mixed_languages(self):
        response = self.client.get(
            self.url,
            {"search": "cosrx سيروم"},
        )

        self.assertEqual(
            self.get_ids(response),
            [self.serum.pk],
        )

    def test_search_variant_sku(self):
        response = self.client.get(
            self.url,
            {"search": "COSRX-30ML"},
        )

        self.assertEqual(
            self.get_ids(response),
            [self.serum.pk],
        )

    def test_exact_name_ranks_first(self):
        response = self.client.get(
            self.url,
            {"search": "Serum"},
        )

        self.assertEqual(
            self.get_ids(response)[0],
            self.hair_serum.pk,
        )

    def test_price_order_overrides_relevance(self):
        response = self.client.get(
            self.url,
            {
                "search": "Serum",
                "ordering": "price_asc",
            },
        )

        self.assertEqual(
            self.get_ids(response),
            [
                self.serum.pk,
                self.hair_serum.pk,
            ],
        )

    def test_search_and_brand_filter(self):
        response = self.client.get(
            self.url,
            {
                "search": "serum",
                "brand": "cosrx",
            },
        )

        self.assertEqual(
            self.get_ids(response),
            [self.serum.pk],
        )

    def test_relevance_requires_search(self):
        response = self.client.get(
            self.url,
            {"ordering": "relevance"},
        )

        self.assertEqual(response.status_code, 400)

    
    def test_fuzzy_english_product_name(self):
        response = self.client.get(
            self.url,
            {"search": "Hydratng"},
        )

        self.assertEqual(response.status_code, 200)

        self.assertIn(
            self.serum.pk,
            self.get_ids(response),
        )

    def test_fuzzy_brand_name(self):
        response = self.client.get(
            self.url,
            {"search": "COSRXX"},
        )

        self.assertEqual(response.status_code, 200)

        self.assertIn(
            self.serum.pk,
            self.get_ids(response),
        )

    def test_fuzzy_arabic_product_name(self):
        response = self.client.get(
            self.url,
            {"search": "سيرووم"},
        )

        self.assertEqual(response.status_code, 200)

        self.assertIn(
            self.serum.pk,
            self.get_ids(response),
        )

    def test_fuzzy_search_with_brand_filter(self):
        response = self.client.get(
            self.url,
            {
                "search": "Hydratng",
                "brand": "cosrx",
            },
        )

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            self.get_ids(response),
            [self.serum.pk],
        )

    def test_unrelated_products_are_excluded(self):
        response = self.client.get(
            self.url,
            {"search": "Hydratng"},
        )

        self.assertNotIn(
            self.cleanser.pk,
            self.get_ids(response),
        )

