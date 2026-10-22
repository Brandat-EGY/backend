
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework.test import APITestCase

from .models import (
    Product,
    ProductVariant,
    Box,
    Order,
    OrderItem,
    OrderBox,
    OrderBoxItem,
)


User = get_user_model()


class AdminOrdersAPITests(APITestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            phone="01011112222",
            customer_name="Admin",
            password="SecurePass2026!",
            is_staff=True,
        )

        self.customer = User.objects.create_user(
            phone="01033334444",
            customer_name="Customer",
            password="SecurePass2026!",
        )

        self.product = Product.objects.create(
            name_ar="سيروم",
            description_ar="سيروم للبشرة",
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            price=Decimal("200.00"),
            stock=6,
        )

        self.box = Box.objects.create(
            name_ar="بوكس العناية",
            description_ar="بوكس للبشرة",
            sku="BOX-ADMIN-ORDER-001",
            price=Decimal("600.00"),
            stock=2,
        )

        self.order = Order.objects.create(
            customer_name="Test Customer",
            phone="01012345678",
            address="Cairo",
            status="pending",
        )

        OrderItem.objects.create(
            order=self.order,
            variant=self.variant,
            quantity=2,
            price=Decimal("150.00"),
        )

        order_box = OrderBox.objects.create(
            order=self.order,
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

        self.detail_url = reverse(
            "admin-order-detail",
            kwargs={"order_id": self.order.pk},
        )

        self.status_url = reverse(
            "admin-order-status",
            kwargs={"order_id": self.order.pk},
        )

        self.cancel_url = reverse(
            "admin-order-cancel",
            kwargs={"order_id": self.order.pk},
        )

        self.client.force_authenticate(
            user=self.admin,
        )

    def test_admin_can_view_order_details(self):
        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["total_price"],
            "800.00",
        )
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(len(response.data["boxes"]), 1)
        self.assertTrue(response.data["is_guest"])

    def test_admin_can_ship_then_deliver(self):
        shipped = self.client.patch(
            self.status_url,
            {"status": "shipped"},
            format="json",
        )

        self.assertEqual(shipped.status_code, 200)
        self.assertTrue(shipped.data["changed"])

        delivered = self.client.patch(
            self.status_url,
            {"status": "delivered"},
            format="json",
        )

        self.assertEqual(delivered.status_code, 200)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "delivered")

    def test_cannot_skip_shipping(self):
        response = self.client.patch(
            self.status_url,
            {"status": "delivered"},
            format="json",
        )

        self.assertEqual(response.status_code, 409)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "pending")

    def test_repeated_status_update_is_safe(self):
        self.client.patch(
            self.status_url,
            {"status": "shipped"},
            format="json",
        )

        response = self.client.patch(
            self.status_url,
            {"status": "shipped"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["changed"])

    def test_cannot_move_shipped_order_back(self):
        self.order.status = "shipped"
        self.order.save(update_fields=["status"])

        response = self.client.patch(
            self.status_url,
            {"status": "pending"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_paid_status_is_not_allowed(self):
        response = self.client.patch(
            self.status_url,
            {"status": "paid"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_cannot_cancel_through_status_endpoint(self):
        response = self.client.patch(
            self.status_url,
            {"status": "cancelled"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_cancel_restores_variant_and_box_stock(self):
        response = self.client.post(self.cancel_url)

        self.assertEqual(response.status_code, 200)

        self.order.refresh_from_db()
        self.variant.refresh_from_db()
        self.box.refresh_from_db()

        self.assertEqual(self.order.status, "cancelled")
        self.assertIsNotNone(
            self.order.stock_restored_at
        )

        # Direct 2 + box contents 2 = 4.
        self.assertEqual(self.variant.stock, 10)
        self.assertEqual(self.box.stock, 3)

    def test_cancellation_twice_does_not_restore_twice(self):
        first = self.client.post(self.cancel_url)
        second = self.client.post(self.cancel_url)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

        self.variant.refresh_from_db()
        self.box.refresh_from_db()

        self.assertEqual(self.variant.stock, 10)
        self.assertEqual(self.box.stock, 3)

    def test_shipped_order_cannot_be_cancelled(self):
        self.order.status = "shipped"
        self.order.save(update_fields=["status"])

        response = self.client.post(self.cancel_url)

        self.assertEqual(response.status_code, 409)

        self.variant.refresh_from_db()
        self.box.refresh_from_db()

        self.assertEqual(self.variant.stock, 6)
        self.assertEqual(self.box.stock, 2)

    def test_cancelled_order_cannot_be_shipped(self):
        self.client.post(self.cancel_url)

        response = self.client.patch(
            self.status_url,
            {"status": "shipped"},
            format="json",
        )

        self.assertEqual(response.status_code, 409)

    def test_normal_customer_cannot_manage_orders(self):
        self.client.force_authenticate(
            user=self.customer,
        )

        detail = self.client.get(self.detail_url)

        update = self.client.patch(
            self.status_url,
            {"status": "shipped"},
            format="json",
        )

        cancel = self.client.post(self.cancel_url)

        self.assertEqual(detail.status_code, 403)
        self.assertEqual(update.status_code, 403)
        self.assertEqual(cancel.status_code, 403)

    def test_missing_order_returns_404(self):
        url = reverse(
            "admin-order-detail",
            kwargs={"order_id": 999999},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_extra_fields_are_rejected(self):
        response = self.client.patch(
            self.status_url,
            {
                "status": "shipped",
                "total_price": "1.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "pending")
