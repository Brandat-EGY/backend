
from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Category


User = get_user_model()


class AdminCategoryTests(APITestCase):

    def setUp(self):
        self.staff = User.objects.create_user(
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

        self.root = Category.objects.create(
            name_ar="العناية بالبشرة",
            name_en="Skincare",
            slug="skincare",
            is_active=True,
        )

        self.child = Category.objects.create(
            name_ar="السيروم",
            name_en="Serums",
            slug="serums",
            parent=self.root,
            is_active=True,
        )

        self.inactive = Category.objects.create(
            name_ar="العناية بالشعر",
            name_en="Haircare",
            slug="haircare",
            is_active=False,
        )

        self.list_url = reverse("admin-category-list")

        self.detail_url = reverse(
            "admin-category-detail",
            kwargs={"category_id": self.child.pk},
        )

        token = RefreshToken.for_user(self.staff)

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {token.access_token}"
        )

    def test_list_includes_active_and_inactive(self):
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)

    def test_create_main_category(self):
        response = self.client.post(
            self.list_url,
            {
                "name_ar": "المكياج",
                "name_en": "Makeup",
                "slug": "makeup",
                "parent": None,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.data["parent"])

    def test_create_subcategory(self):
        response = self.client.post(
            self.list_url,
            {
                "name_ar": "المرطبات",
                "name_en": "Moisturizers",
                "slug": "moisturizers",
                "parent": self.root.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data["parent"],
            self.root.pk,
        )

    def test_duplicate_slug_is_rejected(self):
        response = self.client.post(
            self.list_url,
            {
                "name_ar": "سيروم آخر",
                "name_en": "Another Serum",
                "slug": "SERUMS",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_filter_inactive(self):
        response = self.client.get(
            self.list_url,
            {"is_active": "false"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_filter_root_categories(self):
        response = self.client.get(
            self.list_url,
            {"parent": "root"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)

    def test_update_category(self):
        response = self.client.patch(
            self.detail_url,
            {"name_en": "Face Serums"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.child.refresh_from_db()
        self.assertEqual(
            self.child.name_en,
            "Face Serums",
        )

    def test_deactivate_category(self):
        response = self.client.patch(
            self.detail_url,
            {"is_active": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.child.refresh_from_db()
        self.assertFalse(self.child.is_active)

    def test_category_cannot_be_own_parent(self):
        response = self.client.patch(
            self.detail_url,
            {"parent": self.child.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_cannot_create_parent_cycle(self):
        root_url = reverse(
            "admin-category-detail",
            kwargs={"category_id": self.root.pk},
        )

        response = self.client.patch(
            root_url,
            {"parent": self.child.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_customer_cannot_create_category(self):
        token = RefreshToken.for_user(self.customer)

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {token.access_token}"
        )

        response = self.client.post(
            self.list_url,
            {
                "name_ar": "المكياج",
                "name_en": "Makeup",
                "slug": "makeup",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_extra_fields_are_rejected(self):
        response = self.client.patch(
            self.detail_url,
            {"products": []},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
