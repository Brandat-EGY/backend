
from decimal import Decimal

from django.urls import reverse

from rest_framework.test import APITestCase

from .models import (
    Box,
    BoxImage,
    BoxItem,
    Product,
    ProductVariant,
)


class BoxDetailTests(APITestCase):

    def setUp(self):
        self.product = Product.objects.create(
            name_ar="سيروم مرطب",
            name_en="Hydrating Serum",
            description_ar="سيروم للعناية بالبشرة",
            is_available=True,
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="30ml",
            price=Decimal("200.00"),
            stock=5,
            is_active=True,
        )

        self.box = Box.objects.create(
            name_ar="بوكس العناية",
            name_en="Skincare Box",
            description_ar="بوكس للعناية بالبشرة",
            description_en="Skincare gift box",
            sku="BOX-DETAIL-001",
            price=Decimal("900.00"),
            discount_price=Decimal("800.00"),
            stock=10,
            is_active=True,
        )

        self.item = BoxItem.objects.create(
            box=self.box,
            variant=self.variant,
            quantity=2,
        )

        self.url = reverse(
            "box-detail",
            kwargs={"box_id": self.box.pk},
        )

    def test_guest_can_view_box_details(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            response.data["name_en"],
            "Skincare Box",
        )

        self.assertEqual(
            response.data["description_en"],
            "Skincare gift box",
        )

    def test_box_price_and_stock(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["final_price"],
            "800.00",
        )
        self.assertEqual(
            response.data["available_stock"],
            2,
        )

    def test_box_contains_correct_items(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        items = response.data["items"]

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["quantity"], 2)

        self.assertEqual(
            items[0]["product"]["id"],
            self.product.pk,
        )

        self.assertEqual(
            items[0]["variant"]["sku"],
            self.variant.sku,
        )

    def test_box_images_are_returned(self):
        BoxImage.objects.create(
            box=self.box,
            image="boxes/detail.jpg",
            is_main=True,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(response.data["images"]),
            1,
        )
        self.assertTrue(
            response.data["images"][0]["is_main"]
        )

    def test_inactive_box_returns_404(self):
        self.box.is_active = False
        self.box.save(update_fields=["is_active"])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_nonexistent_box_returns_404(self):
        url = reverse(
            "box-detail",
            kwargs={"box_id": 999999},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)
