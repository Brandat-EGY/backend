
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework.test import APITestCase, APIClient

from .models import (
    Box,
    Order,
    OrderItem,
    OrderBox,
    OrderBoxItem,
    Product,
    ProductVariant,
)


User = get_user_model()


class CustomerOrdersAPITests(APITestCase):

    def setUp(self):
        self.list_url = reverse(
            "customer-order-list"
        )

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

        session = self.client.session
        session["test_marker"] = True
        session.save()

        self.session_key = session.session_key

        self.guest_order = Order.objects.create(
            session_key=self.session_key,
            customer_name="Guest Customer",
            phone="01012345678",
            address="Cairo",
        )

        self.user_order = Order.objects.create(
            user=self.user,
            customer_name="Registered Customer",
            phone="01011112222",
            address="Giza",
        )

        self.other_order = Order.objects.create(
            user=self.other_user,
            customer_name="Other Customer",
            phone="01033334444",
            address="Alexandria",
        )

        self.product = Product.objects.create(
            name_ar="سيروم مرطب",
            description_ar="سيروم للبشرة",
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            price=Decimal("200.00"),
            stock=10,
        )

        self.box = Box.objects.create(
            name_ar="بوكس العناية",
            description_ar="بوكس للبشرة",
            sku="BOX-ORDER-001",
            price=Decimal("600.00"),
            stock=5,
        )

        OrderItem.objects.create(
            order=self.guest_order,
            variant=self.variant,
            quantity=2,
            price=Decimal("150.00"),
        )

        order_box = OrderBox.objects.create(
            order=self.guest_order,
            box=self.box,
            name_ar=self.box.name_ar,
            name_en=self.box.name_en,
            sku=self.box.sku,
            quantity=1,
            price=Decimal("500.00"),
        )

        OrderBoxItem.objects.create(
            order_box=order_box,
            variant=self.variant,
            sku=self.variant.sku,
            product_name_ar=self.product.name_ar,
            product_name_en=self.product.name_en,
            quantity=2,
        )

    def detail_url(self, order):
        return reverse(
            "customer-order-detail",
            kwargs={"order_id": order.pk},
        )

    def test_guest_sees_own_session_orders(self):
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

        self.assertEqual(
            response.data["results"][0]["id"],
            self.guest_order.pk,
        )

    def test_guest_can_see_order_details(self):
        response = self.client.get(
            self.detail_url(self.guest_order)
        )

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            response.data["total_price"],
            "800.00",
        )

        self.assertEqual(
            response.data["payment_method"],
            "cash_on_delivery",
        )

        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(len(response.data["boxes"]), 1)

    def test_guest_cannot_access_registered_order(self):
        response = self.client.get(
            self.detail_url(self.user_order)
        )

        self.assertEqual(response.status_code, 404)

    def test_logged_in_user_sees_only_own_orders(self):
        self.client.force_authenticate(
            user=self.user
        )

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

        self.assertEqual(
            response.data["results"][0]["id"],
            self.user_order.pk,
        )

    def test_user_cannot_access_another_users_order(self):
        self.client.force_authenticate(
            user=self.user
        )

        response = self.client.get(
            self.detail_url(self.other_order)
        )

        self.assertEqual(response.status_code, 404)

    def test_prices_are_saved_at_checkout(self):
        self.variant.price = Decimal("300.00")
        self.variant.save(update_fields=["price"])

        self.box.price = Decimal("900.00")
        self.box.save(update_fields=["price"])

        response = self.client.get(
            self.detail_url(self.guest_order)
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["total_price"],
            "800.00",
        )

    def test_guest_without_session_sees_no_orders(self):
        another_client = APIClient()

        response = another_client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
