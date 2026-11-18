
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework.test import APITestCase

from .models import (
    Box,
    BoxItem,
    Product,
    ProductVariant,
)


User = get_user_model()


class AdminBoxTests(APITestCase):

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
            name_ar="سيروم مرطب",
            name_en="Hydrating Serum",
            description_ar="سيروم للبشرة",
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="30ml",
            price=Decimal("200.00"),
            stock=10,
        )

        self.box = Box.objects.create(
            name_ar="بوكس الترطيب",
            name_en="Hydration Box",
            description_ar="بوكس للبشرة",
            sku="BOX-TEST-001",
            price=Decimal("900.00"),
            discount_price=Decimal("800.00"),
            stock=5,
            is_active=False,
        )

        BoxItem.objects.create(
            box=self.box,
            variant=self.variant,
            quantity=2,
        )

        self.list_url = reverse(
            "admin-box-list"
        )

        self.detail_url = reverse(
            "admin-box-detail",
            kwargs={"box_id": self.box.pk},
        )

        self.client.force_authenticate(
            user=self.admin
        )

    def test_admin_can_list_draft_boxes(self):
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertFalse(
            response.data["results"][0]["is_active"]
        )

    def test_create_box_starts_as_draft(self):
        response = self.client.post(
            self.list_url,
            {
                "name_ar": "بوكس جديد",
                "name_en": "New Box",
                "description_ar": "بوكس عناية جديد",
                "sku": "box-new-001",
                "price": "500.00",
                "stock": 10,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data["is_active"])
        self.assertEqual(
            response.data["sku"],
            "BOX-NEW-001",
        )

    def test_admin_can_view_box_items(self):
        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["items_count"],
            1,
        )
        self.assertEqual(
            len(response.data["items"]),
            1,
        )
        self.assertEqual(
            response.data["items"][0]["variant"]["id"],
            self.variant.pk,
        )

    def test_admin_can_update_box(self):
        response = self.client.patch(
            self.detail_url,
            {
                "price": "1000.00",
                "discount_price": "850.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.box.refresh_from_db()
        self.assertEqual(
            self.box.price,
            Decimal("1000.00"),
        )

    def test_invalid_discount_is_rejected(self):
        response = self.client.patch(
            self.detail_url,
            {"discount_price": "950.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_duplicate_sku_is_rejected(self):
        response = self.client.post(
            self.list_url,
            {
                "name_ar": "بوكس آخر",
                "description_ar": "وصف آخر",
                "sku": "box-test-001",
                "price": "500.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_box_cannot_be_published_by_patch(self):
        response = self.client.patch(
            self.detail_url,
            {"is_active": True},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

        self.box.refresh_from_db()
        self.assertFalse(self.box.is_active)

    def test_filter_inactive_boxes(self):
        Box.objects.create(
            name_ar="بوكس منشور",
            description_ar="بوكس آخر",
            sku="BOX-ACTIVE-001",
            price=Decimal("500.00"),
            is_active=True,
        )

        response = self.client.get(
            self.list_url,
            {"is_active": "false"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_customer_cannot_modify_boxes(self):
        self.client.force_authenticate(
            user=self.customer
        )

        response = self.client.patch(
            self.detail_url,
            {"price": "100.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_public_cannot_view_draft_box(self):
        self.client.force_authenticate(user=None)

        url = reverse(
            "box-detail",
            kwargs={"box_id": self.box.pk},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)
