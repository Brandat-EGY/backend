
from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from .models import Collection, Box


class CollectionListTests(APITestCase):

    def setUp(self):
        self.url = reverse("collection-list")

        self.collection = Collection.objects.create(
            name_ar="العناية الكورية",
            name_en="Korean Skincare",
            slug="korean-skincare",
            is_active=True,
        )

        self.active_box = Box.objects.create(
            name_ar="بوكس الترطيب",
            name_en="Hydration Box",
            description_ar="بوكس ترطيب البشرة",
            sku="BOX-COL-001",
            price=Decimal("500.00"),
            stock=5,
            is_active=True,
        )

        self.inactive_box = Box.objects.create(
            name_ar="بوكس النضارة",
            name_en="Glow Box",
            description_ar="بوكس نضارة البشرة",
            sku="BOX-COL-002",
            price=Decimal("600.00"),
            stock=5,
            is_active=False,
        )

        self.collection.boxes.add(
            self.active_box,
            self.inactive_box,
        )

    def test_guest_can_list_collections(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_only_active_boxes_are_counted(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        collection = response.data["results"][0]

        self.assertEqual(
            collection["boxes_count"],
            1,
        )

    def test_inactive_collection_is_hidden(self):
        self.collection.is_active = False
        self.collection.save(
            update_fields=["is_active"]
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)


def test_collection_detail_returns_active_boxes(self):
    url = reverse(
        "collection-detail",
        kwargs={"slug": self.collection.slug},
    )

    response = self.client.get(url)

    self.assertEqual(response.status_code, 200)
    self.assertEqual(
        response.data["slug"],
        "korean-skincare",
    )
    self.assertEqual(
        response.data["boxes_count"],
        1,
    )

    boxes = response.data["boxes"]

    self.assertEqual(len(boxes), 1)
    self.assertEqual(
        boxes[0]["id"],
        self.active_box.pk,
    )

    self.assertIn("final_price", boxes[0])
    self.assertIn("available_stock", boxes[0])
    self.assertIn("in_stock", boxes[0])


def test_inactive_collection_detail_returns_404(self):
    self.collection.is_active = False
    self.collection.save(update_fields=["is_active"])

    url = reverse(
        "collection-detail",
        kwargs={"slug": self.collection.slug},
    )

    response = self.client.get(url)

    self.assertEqual(response.status_code, 404)


def test_nonexistent_collection_returns_404(self):
    url = reverse(
        "collection-detail",
        kwargs={"slug": "not-found"},
    )

    response = self.client.get(url)

    self.assertEqual(response.status_code, 404)
