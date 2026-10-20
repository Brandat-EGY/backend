
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    DailyOffer,
    Favorite,
    Order,
    OrderItem,
    Product,
    ProductImage,
    ProductVariant,
    Review,
)


User = get_user_model()


class ProductDetailAPITests(APITestCase):

    def setUp(self):
        self.product = Product.objects.create(
            name_ar="سيروم مرطب",
            name_en="Hydrating Serum",
            description_ar="سيروم لترطيب البشرة",
            description_en="Hydrating face serum",
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku="SERUM-30ML",
            size="30ml",
            price=Decimal("500.00"),
            discount_price=Decimal("450.00"),
            stock=5,
        )

        self.out_of_stock_variant = (
            ProductVariant.objects.create(
                product=self.product,
                sku="SERUM-50ML",
                price=Decimal("200.00"),
                stock=0,
            )
        )

        self.inactive_variant = ProductVariant.objects.create(
            product=self.product,
            sku="SERUM-INACTIVE",
            price=Decimal("100.00"),
            stock=10,
            is_active=False,
        )

        now = timezone.now()

        self.offer = DailyOffer.objects.create(
            variant=self.variant,
            price=Decimal("380.00"),
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=1),
            is_active=True,
        )

        self.url = reverse(
            "product-detail",
            kwargs={"product_id": self.product.pk},
        )

    def test_product_detail_and_effective_price(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["name_en"],
            "Hydrating Serum",
        )

        self.assertEqual(
            response.data["starting_price"],
            "380.00",
        )

        self.assertTrue(response.data["in_stock"])

        variants = response.data["variants"]

        # Inactive variants must not be displayed.
        self.assertEqual(len(variants), 2)

        variant = next(
            item for item in variants
            if item["sku"] == "SERUM-30ML"
        )

        self.assertEqual(
            variant["final_price"],
            "380.00",
        )
        self.assertTrue(variant["can_purchase"])

    def test_out_of_stock_variant_is_visible(self):
        response = self.client.get(self.url)

        variant = next(
            item for item in response.data["variants"]
            if item["sku"] == "SERUM-50ML"
        )

        self.assertEqual(variant["stock"], 0)
        self.assertFalse(variant["can_purchase"])

    def test_out_of_stock_product_is_visible(self):
        self.variant.stock = 0
        self.variant.save(update_fields=["stock"])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["in_stock"])
        self.assertIsNone(
            response.data["starting_price"]
        )

    def test_expired_offer_is_ignored(self):
        self.offer.ends_at = timezone.now() - timedelta(
            minutes=1
        )
        self.offer.save(update_fields=["ends_at"])

        response = self.client.get(self.url)

        variant = next(
            item for item in response.data["variants"]
            if item["sku"] == "SERUM-30ML"
        )

        self.assertEqual(
            variant["final_price"],
            "450.00",
        )
        self.assertEqual(
            response.data["starting_price"],
            "450.00",
        )

    def test_unavailable_product_returns_404(self):
        self.product.is_available = False
        self.product.save(update_fields=["is_available"])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_product_not_found(self):
        url = reverse(
            "product-detail",
            kwargs={"product_id": 999999},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_guest_favorite_status(self):
        session = self.client.session
        session["favorite_products_v1"] = [
            self.product.pk
        ]
        session.save()

        response = self.client.get(self.url)

        self.assertTrue(
            response.data["is_favorite"]
        )

    def test_authenticated_favorite_status(self):
        user = User.objects.create_user(
            phone="01088888888",
            customer_name="Test Customer",
            password="SecurePass2026!",
        )

        Favorite.objects.create(
            user=user,
            product=self.product,
        )

        refresh = RefreshToken.for_user(user)

        self.client.credentials(
            HTTP_AUTHORIZATION=(
                f"Bearer {refresh.access_token}"
            )
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.data["is_favorite"]
        )

    def test_main_image_is_first(self):
        ProductImage.objects.create(
            product=self.product,
            image="products/other.jpg",
            is_main=False,
        )

        ProductImage.objects.create(
            product=self.product,
            image="products/main.jpg",
            is_main=True,
        )

        response = self.client.get(self.url)

        images = response.data["images"]

        self.assertEqual(len(images), 2)
        self.assertTrue(images[0]["is_main"])
        self.assertTrue(
            response.data["main_image"].endswith(
                "/products/main.jpg"
            )
        )

    def test_review_statistics(self):
        order = Order.objects.create(
            customer_name="Test Customer",
            phone="01000000000",
            address="Cairo",
        )

        order_item = OrderItem.objects.create(
            order=order,
            variant=self.variant,
            quantity=1,
            price=Decimal("380.00"),
        )

        Review.objects.create(
            order_item=order_item,
            rating=5,
            name="Customer",
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["reviews_count"],
            1,
        )
        self.assertEqual(
            response.data["average_rating"],
            5.0,
        )
