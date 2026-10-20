from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from .models import (
    Brand,
    Category,
    Product,
    ProductVariant,
)


class ArabicSearchNormalizationTests(APITestCase):

    def setUp(self):
        self.url = reverse("product-list")

        brand = Brand.objects.create(
            name_ar="إكْسيس واي",
            name_en="Axis Y",
            slug="axis-y",
        )

        category = Category.objects.create(
            name_ar="العِنايَة بالبَشَرَة",
            name_en="Skin Care",
            slug="skin-care",
        )

        self.product = Product.objects.create(
            name_ar="سيروم مُرَطِّب للبَشَرَة",
            name_en="Hydrating Serum",
            description_ar="منتج للعناية بالبشرة",
            brand=brand,
            category=category,
        )

        ProductVariant.objects.create(
            product=self.product,
            sku="AXIS-SERUM-30",
            shade_ar="فَاتِحَة",
            price=Decimal("200.00"),
            stock=5,
        )

    def assert_product_found(self, search):
        response = self.client.get(
            self.url,
            {"search": search},
        )

        self.assertEqual(response.status_code, 200)

        self.assertIn(
            self.product.pk,
            [
                item["id"]
                for item in response.data["results"]
            ],
        )

    def test_arabic_without_diacritics(self):
        self.assert_product_found("سيروم مرطب")

    def test_alef_normalization(self):
        self.assert_product_found("اكسيس")

    def test_taa_marbuta_normalization(self):
        self.assert_product_found("بشره")

    def test_category_normalization(self):
        self.assert_product_found("العناية")

    def test_variant_shade_normalization(self):
        self.assert_product_found("فاتحه")

    def test_mixed_arabic_english(self):
        self.assert_product_found("اكسيس Hydrating")
