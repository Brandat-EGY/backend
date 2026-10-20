
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Favorite, Product, ProductVariant


User = get_user_model()


class ProductListAPITests(APITestCase):

    def setUp(self):
        self.url = reverse("product-list")

        self.product = Product.objects.create(
            name_ar="سيرم للبشرة",
            name_en="Face Serum",
            description_ar="سيرم للعناية بالبشرة",
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku="SERUM-30ML",
            size="30ml",
            price=Decimal("350.00"),
            stock=5,
        )

    def test_product_list_returns_starting_price(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

        product = response.data["results"][0]

        self.assertEqual(
            Decimal(product["starting_price"]),
            Decimal("350.00"),
        )
        self.assertTrue(product["in_stock"])
        self.assertFalse(product["is_favorite"])

    def test_out_of_stock_product_is_visible(self):
        self.variant.stock = 0
        self.variant.save(update_fields=["stock"])

        response = self.client.get(self.url)

        self.assertEqual(response.data["count"], 1)

        product = response.data["results"][0]

        self.assertFalse(product["in_stock"])
        self.assertIsNone(product["starting_price"])

    def test_unavailable_product_is_hidden(self):
        self.product.is_available = False
        self.product.save(update_fields=["is_available"])

        response = self.client.get(self.url)

        self.assertEqual(response.data["count"], 0)

    def test_pagination(self):
        for i in range(24):
            Product.objects.create(
                name_ar=f"منتج {i}",
                description_ar="منتج تجريبي",
            )

        first_page = self.client.get(
            self.url,
            {"page": 1},
        )

        second_page = self.client.get(
            self.url,
            {"page": 2},
        )

        self.assertEqual(first_page.data["count"], 25)
        self.assertEqual(
            len(first_page.data["results"]),
            24,
        )
        self.assertEqual(
            len(second_page.data["results"]),
            1,
        )

        first_ids = {
            item["id"]
            for item in first_page.data["results"]
        }

        second_ids = {
            item["id"]
            for item in second_page.data["results"]
        }

        self.assertTrue(first_ids.isdisjoint(second_ids))

    def test_guest_favorite_status(self):
        session = self.client.session
        session["favorite_products_v1"] = [self.product.pk]
        session.save()

        response = self.client.get(self.url)

        self.assertTrue(
            response.data["results"][0]["is_favorite"]
        )

    def test_authenticated_favorite_status(self):
        user = User.objects.create_user(
            phone="01099999999",
            customer_name="Test Customer",
            password="SecurePass2026!",
        )

        Favorite.objects.create(
            user=user,
            product=self.product,
        )

        token = RefreshToken.for_user(user)

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {token.access_token}"
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        self.assertTrue(
            response.data["results"][0]["is_favorite"]
        )
