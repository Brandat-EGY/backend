
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework.test import APITestCase

from .models import Box, Collection


User = get_user_model()


class AdminCollectionTests(APITestCase):

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

        self.collection = Collection.objects.create(
            name_ar="العناية الكورية",
            name_en="Korean Skincare",
            slug="korean-skincare",
            is_active=False,
        )

        self.box = Box.objects.create(
            name_ar="بوكس العناية",
            description_ar="بوكس للعناية بالبشرة",
            sku="BOX-COL-ADMIN-001",
            price=Decimal("500.00"),
            stock=10,
            is_active=True,
        )

        self.list_url = reverse(
            "admin-collection-list"
        )

        self.detail_url = reverse(
            "admin-collection-detail",
            kwargs={
                "collection_id": self.collection.pk
            },
        )

        self.add_box_url = reverse(
            "admin-collection-box-add",
            kwargs={
                "collection_id": self.collection.pk
            },
        )

        self.remove_box_url = reverse(
            "admin-collection-box-remove",
            kwargs={
                "collection_id": self.collection.pk,
                "box_id": self.box.pk,
            },
        )

        self.publish_url = reverse(
            "admin-collection-publish",
            kwargs={
                "collection_id": self.collection.pk
            },
        )

        self.unpublish_url = reverse(
            "admin-collection-unpublish",
            kwargs={
                "collection_id": self.collection.pk
            },
        )

        self.client.force_authenticate(
            user=self.admin
        )

    def add_box(self):
        return self.client.post(
            self.add_box_url,
            {"box_id": self.box.pk},
            format="json",
        )

    def test_list_includes_draft_collections(self):
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertFalse(
            response.data["results"][0]["is_active"]
        )

    def test_create_collection_as_draft(self):
        response = self.client.post(
            self.list_url,
            {
                "name_ar": "العناية بالشعر",
                "name_en": "Haircare",
                "slug": "haircare",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data["is_active"])

    def test_update_collection(self):
        response = self.client.patch(
            self.detail_url,
            {"name_en": "Korean Beauty"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.collection.refresh_from_db()
        self.assertEqual(
            self.collection.name_en,
            "Korean Beauty",
        )

    def test_duplicate_slug_rejected(self):
        response = self.client.post(
            self.list_url,
            {
                "name_ar": "مجموعة جديدة",
                "slug": "KOREAN-SKINCARE",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_add_box(self):
        response = self.add_box()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            self.collection.boxes.filter(
                pk=self.box.pk
            ).exists()
        )

    def test_duplicate_box_rejected(self):
        self.add_box()

        response = self.add_box()

        self.assertEqual(response.status_code, 409)

    def test_detail_returns_boxes(self):
        self.add_box()

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["boxes_count"],
            1,
        )
        self.assertEqual(
            response.data["boxes"][0]["id"],
            self.box.pk,
        )

    def test_remove_box_without_deleting_box(self):
        self.add_box()

        response = self.client.delete(
            self.remove_box_url
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            self.collection.boxes.exists()
        )
        self.assertTrue(
            Box.objects.filter(pk=self.box.pk).exists()
        )

    def test_cannot_publish_empty_collection(self):
        response = self.client.post(
            self.publish_url
        )

        self.assertEqual(response.status_code, 400)

    def test_publish_and_public_visibility(self):
        self.add_box()

        response = self.client.post(
            self.publish_url
        )

        self.assertEqual(response.status_code, 200)

        self.collection.refresh_from_db()
        self.assertTrue(self.collection.is_active)

        public_url = reverse(
            "collection-detail",
            kwargs={"slug": self.collection.slug},
        )

        public_response = self.client.get(
            public_url
        )

        self.assertEqual(
            public_response.status_code, 200
        )
        self.assertEqual(
            public_response.data["boxes_count"],
            1,
        )

    def test_cannot_remove_box_from_published_collection(self):
        self.add_box()
        self.client.post(self.publish_url)

        response = self.client.delete(
            self.remove_box_url
        )

        self.assertEqual(response.status_code, 400)

    def test_unpublish_allows_removing_boxes(self):
        self.add_box()
        self.client.post(self.publish_url)

        response = self.client.post(
            self.unpublish_url
        )

        self.assertEqual(response.status_code, 200)

        remove_response = self.client.delete(
            self.remove_box_url
        )

        self.assertEqual(remove_response.status_code, 204)

    def test_non_admin_cannot_manage_collections(self):
        self.client.force_authenticate(
            user=self.customer
        )

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 403)

    def test_cannot_activate_using_patch(self):
        response = self.client.patch(
            self.detail_url,
            {"is_active": True},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
