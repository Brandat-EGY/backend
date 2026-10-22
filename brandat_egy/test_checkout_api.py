
from decimal import Decimal

from django.urls import reverse

from rest_framework.test import APITestCase

from .cart import Cart
from .models import (
    Box,
    BoxItem,
    Order,
    OrderItem,
    OrderBox,
    Product,
    ProductVariant,
)


class CheckoutAPITests(APITestCase):

    def setUp(self):
        self.url = reverse("checkout")

        self.customer_data = {
            "customer_name": "Mohamed Reda",
            "phone": "01012345678",
            "email": "customer@example.com",
            "address": "Cairo, Nasr City",
        }

        self.product = Product.objects.create(
            name_ar="سيروم مرطب",
            description_ar="سيروم للعناية بالبشرة",
            is_available=True,
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            price=Decimal("200.00"),
            stock=5,
            is_active=True,
        )

        self.box = Box.objects.create(
            name_ar="بوكس الترطيب",
            description_ar="بوكس للعناية بالبشرة",
            sku="BOX-CHECKOUT-001",
            price=Decimal("500.00"),
            stock=3,
            is_active=True,
        )

        BoxItem.objects.create(
            box=self.box,
            variant=self.variant,
            quantity=2,
        )

    def set_cart(self, items):
        session = self.client.session
        session[Cart.SESSION_KEY] = items
        session.save()

    def test_guest_checkout_creates_order(self):
        self.set_cart({
            f"variant:{self.variant.pk}": {
                "quantity": 1,
            },
            f"box:{self.box.pk}": {
                "quantity": 1,
            },
        })

        response = self.client.post(
            self.url,
            self.customer_data,
            format="json",
        )

        self.assertEqual(response.status_code, 201)

        order = Order.objects.get(
            pk=response.data["order_id"]
        )

        self.assertIsNone(order.user)
        self.assertEqual(order.status, "pending")
        self.assertEqual(
            order.total_price,
            Decimal("700.00"),
        )

        self.assertEqual(
            OrderItem.objects.filter(order=order).count(),
            1,
        )

        self.assertEqual(
            OrderBox.objects.filter(order=order).count(),
            1,
        )

        self.variant.refresh_from_db()
        self.box.refresh_from_db()

        # One direct variant + two inside the box.
        self.assertEqual(self.variant.stock, 2)
        self.assertEqual(self.box.stock, 2)

    def test_empty_cart_is_rejected(self):
        response = self.client.post(
            self.url,
            self.customer_data,
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_combined_stock_shortage_is_rejected(self):
        self.set_cart({
            f"variant:{self.variant.pk}": {
                "quantity": 4,
            },
            f"box:{self.box.pk}": {
                "quantity": 1,
            },
        })

        response = self.client.post(
            self.url,
            self.customer_data,
            format="json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Order.objects.count(), 0)

        self.variant.refresh_from_db()
        self.box.refresh_from_db()

        self.assertEqual(self.variant.stock, 5)
        self.assertEqual(self.box.stock, 3)

    def test_invalid_customer_data_is_rejected(self):
        self.set_cart({
            f"variant:{self.variant.pk}": {
                "quantity": 1,
            },
        })

        response = self.client.post(
            self.url,
            {
                "customer_name": "",
                "phone": "",
                "address": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_client_cannot_set_price_or_status(self):
        self.set_cart({
            f"variant:{self.variant.pk}": {
                "quantity": 1,
            },
        })

        response = self.client.post(
            self.url,
            {
                **self.customer_data,
                "status": "paid",
                "total_price": "1.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_discount_price_is_saved_in_order(self):
        self.variant.discount_price = Decimal("150.00")
        self.variant.save(
            update_fields=["discount_price"]
        )

        self.set_cart({
            f"variant:{self.variant.pk}": {
                "quantity": 2,
            },
        })

        response = self.client.post(
            self.url,
            self.customer_data,
            format="json",
        )

        self.assertEqual(response.status_code, 201)

        order_item = OrderItem.objects.get(
            order_id=response.data["order_id"]
        )

        self.assertEqual(
            order_item.price,
            Decimal("150.00"),
        )
        self.assertEqual(
            response.data["total_price"],
            "300.00",
        )
