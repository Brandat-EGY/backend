
from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from .cart import Cart
from .models import (
    Product,
    ProductVariant,
    Box,
    BoxItem,
)


class CartDetailAPITests(APITestCase):

    def setUp(self):
        self.url = reverse("cart-detail")

        self.product = Product.objects.create(
            name_ar="سيروم مرطب",
            description_ar="سيروم للبشرة",
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
            sku="BOX-CART-001",
            price=Decimal("500.00"),
            stock=3,
            is_active=True,
        )

        BoxItem.objects.create(
            box=self.box,
            variant=self.variant,
            quantity=2,
        )

    def test_guest_can_view_empty_cart(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["items"], [])
        self.assertEqual(
            response.data["total_price"],
            "0.00",
        )

    def test_guest_can_view_variant_and_box(self):
        session = self.client.session

        session[Cart.SESSION_KEY] = {
            f"variant:{self.variant.pk}": {
                "quantity": 1
            },
            f"box:{self.box.pk}": {
                "quantity": 1
            },
        }

        session.save()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(
            response.data["total_quantity"],
            2,
        )
        self.assertEqual(
            response.data["total_price"],
            "700.00",
        )

        types = {
            item["type"]
            for item in response.data["items"]
        }

        self.assertEqual(types, {"variant", "box"})

    def test_missing_item_returns_conflict(self):
        session = self.client.session

        session[Cart.SESSION_KEY] = {
            "variant:999999": {
                "quantity": 1
            },
        }

        session.save()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 409)



class CartItemAddAPITests(APITestCase):

    def setUp(self):
        self.url = reverse("cart-item-add")

        self.product = Product.objects.create(
            name_ar="سيروم مرطب",
            description_ar="سيروم للبشرة",
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
            sku="BOX-ADD-001",
            price=Decimal("500.00"),
            stock=3,
            is_active=True,
        )

        BoxItem.objects.create(
            box=self.box,
            variant=self.variant,
            quantity=2,
        )

    def test_add_variant(self):
        response = self.client.post(
            self.url,
            {
                "type": "variant",
                "item_id": self.variant.pk,
                "quantity": 2,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data["item"]["quantity"], 2
        )
        self.assertEqual(
            response.data["item"]["price"], "200.00"
        )

    def test_add_same_variant_increases_quantity(self):
        payload = {
            "type": "variant",
            "item_id": self.variant.pk,
            "quantity": 2,
        }

        self.client.post(
            self.url, payload, format="json"
        )

        payload["quantity"] = 1

        response = self.client.post(
            self.url, payload, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["created"])
        self.assertEqual(
            response.data["item"]["quantity"], 3
        )

    def test_add_box(self):
        response = self.client.post(
            self.url,
            {
                "type": "box",
                "item_id": self.box.pk,
                "quantity": 1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data["item"]["key"],
            f"box:{self.box.pk}",
        )

    def test_quantity_exceeds_stock(self):
        response = self.client.post(
            self.url,
            {
                "type": "variant",
                "item_id": self.variant.pk,
                "quantity": 10,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 409)

    def test_invalid_quantity(self):
        response = self.client.post(
            self.url,
            {
                "type": "variant",
                "item_id": self.variant.pk,
                "quantity": 0,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_unpublished_product_cannot_be_added(self):
        self.product.is_available = False
        self.product.save(
            update_fields=["is_available"]
        )

        response = self.client.post(
            self.url,
            {
                "type": "variant",
                "item_id": self.variant.pk,
                "quantity": 1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 409)

    def test_nonexistent_item_returns_404(self):
        response = self.client.post(
            self.url,
            {
                "type": "variant",
                "item_id": 999999,
                "quantity": 1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 404)



class CartUpdateDeleteAPITests(APITestCase):

    def setUp(self):
        self.product = Product.objects.create(
            name_ar="سيروم مرطب",
            description_ar="سيروم للبشرة",
            is_available=True,
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            price=Decimal("200.00"),
            stock=5,
            is_active=True,
        )

        self.item_key = f"variant:{self.variant.pk}"

        self.item_url = reverse(
            "cart-item-detail",
            kwargs={"item_key": self.item_key},
        )

        self.cart_url = reverse("cart-detail")

        session = self.client.session
        session[Cart.SESSION_KEY] = {
            self.item_key: {"quantity": 3}
        }
        session.save()

    def test_update_quantity(self):
        response = self.client.patch(
            self.item_url,
            {"quantity": 2},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["item"]["quantity"], 2
        )

        cart_response = self.client.get(self.cart_url)

        self.assertEqual(
            cart_response.data["total_price"],
            "400.00",
        )

    def test_update_exceeds_stock(self):
        response = self.client.patch(
            self.item_url,
            {"quantity": 10},
            format="json",
        )

        self.assertEqual(response.status_code, 409)

        cart_response = self.client.get(self.cart_url)

        self.assertEqual(
            cart_response.data["items"][0]["quantity"],
            3,
        )

    def test_zero_quantity_is_rejected(self):
        response = self.client.patch(
            self.item_url,
            {"quantity": 0},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_delete_cart_item(self):
        response = self.client.delete(self.item_url)

        self.assertEqual(response.status_code, 204)

        cart_response = self.client.get(self.cart_url)

        self.assertEqual(cart_response.data["count"], 0)

    def test_clear_cart(self):
        response = self.client.delete(self.cart_url)

        self.assertEqual(response.status_code, 204)

        cart_response = self.client.get(self.cart_url)

        self.assertEqual(cart_response.data["items"], [])

    def test_missing_cart_item_returns_404(self):
        url = reverse(
            "cart-item-detail",
            kwargs={"item_key": "variant:999999"},
        )

        response = self.client.patch(
            url,
            {"quantity": 1},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_invalid_cart_key_returns_400(self):
        url = reverse(
            "cart-item-detail",
            kwargs={"item_key": "invalid:1"},
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, 400)
