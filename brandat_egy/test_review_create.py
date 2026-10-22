
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework.test import APITestCase

from .models import (
    Order,
    OrderItem,
    Product,
    ProductVariant,
    Review,
)


User = get_user_model()


class ReviewCreateAPITests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone="01011112222",
            customer_name="Customer One",
            password="SecurePass2026!",
        )

        self.other_user = User.objects.create_user(
            phone="01033334444",
            customer_name="Customer Two",
            password="SecurePass2026!",
        )

        self.product = Product.objects.create(
            name_ar="سيروم مرطب",
            description_ar="سيروم للبشرة",
            is_available=True,
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            price=Decimal("200.00"),
            stock=10,
        )

        self.order = Order.objects.create(
            user=self.user,
            customer_name="Customer One",
            phone="01011112222",
            address="Cairo",
            status="delivered",
        )

        self.order_item = OrderItem.objects.create(
            order=self.order,
            variant=self.variant,
            quantity=1,
            price=Decimal("200.00"),
        )

        self.url = reverse(
            "product-reviews",
            kwargs={"product_id": self.product.pk},
        )

        self.payload = {
            "order_item_id": self.order_item.pk,
            "name": "Buyer",
            "rating": 5,
            "comment": "Excellent product",
        }

    def test_customer_can_review_delivered_purchase(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["rating"], 5)

        self.assertTrue(
            Review.objects.filter(
                order_item=self.order_item
            ).exists()
        )

    def test_pending_order_cannot_be_reviewed(self):
        self.order.status = "pending"
        self.order.save(update_fields=["status"])

        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Review.objects.count(), 0)

    def test_customer_cannot_review_another_users_order(self):
        self.client.force_authenticate(
            user=self.other_user
        )

        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Review.objects.count(), 0)

    def test_duplicate_review_is_rejected(self):
        self.client.force_authenticate(user=self.user)

        first = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        second = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(Review.objects.count(), 1)

    def test_invalid_rating_is_rejected(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            {
                **self.payload,
                "rating": 6,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Review.objects.count(), 0)

    def test_guest_cannot_review_registered_order(self):
        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_guest_can_review_own_session_purchase(self):
        session = self.client.session
        session["test_marker"] = True
        session.save()

        guest_order = Order.objects.create(
            user=None,
            session_key=session.session_key,
            customer_name="Guest Customer",
            phone="01012345678",
            address="Cairo",
            status="delivered",
        )

        guest_item = OrderItem.objects.create(
            order=guest_order,
            variant=self.variant,
            quantity=1,
            price=Decimal("200.00"),
        )

        response = self.client.post(
            self.url,
            {
                "order_item_id": guest_item.pk,
                "rating": 4,
                "comment": "Good product",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            Review.objects.filter(
                order_item=guest_item
            ).exists()
        )

    def test_created_review_appears_in_public_list(self):
        self.client.force_authenticate(user=self.user)

        self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["rating"],
            5,
        )
