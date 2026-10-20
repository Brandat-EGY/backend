
from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Brand


User = get_user_model()


class AdminBrandTests(APITestCase):

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

        self.brand = Brand.objects.create(
            name_ar="كوسركس",
            name_en="COSRX",
            slug="cosrx",
            is_active=True,
        )

        self.list_url = reverse("admin-brand-list")

        self.detail_url = reverse(
            "admin-brand-detail",
            kwargs={"brand_id": self.brand.pk},
        )

    def authenticate(self, user):
        token = RefreshToken.for_user(user)

        self.client.credentials(
            HTTP_AUTHORIZATION=(
                f"Bearer {token.access_token}"
            )
        )

    def test_staff_can_list_brands(self):
        self.authenticate(self.staff)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_staff_can_create_brand(self):
        self.authenticate(self.staff)

        response = self.client.post(
            self.list_url,
            {
                "name_ar": "أنوا",
                "name_en": "ANUA",
                "slug": "anua",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            Brand.objects.filter(slug="anua").exists()
        )

    def test_duplicate_slug_is_rejected(self):
        self.authenticate(self.staff)

        response = self.client.post(
            self.list_url,
            {
                "name_ar": "كوسركس 2",
                "name_en": "COSRX 2",
                "slug": "COSRX",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("slug", response.data)

    def test_staff_can_update_brand(self):
        self.authenticate(self.staff)

        response = self.client.patch(
            self.detail_url,
            {"name_en": "COSRX Korea"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.brand.refresh_from_db()
        self.assertEqual(
            self.brand.name_en,
            "COSRX Korea",
        )

    def test_staff_can_deactivate_brand(self):
        self.authenticate(self.staff)

        response = self.client.patch(
            self.detail_url,
            {"is_active": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.brand.refresh_from_db()
        self.assertFalse(self.brand.is_active)

    def test_filter_inactive_brands(self):
        self.authenticate(self.staff)

        self.brand.is_active = False
        self.brand.save(update_fields=["is_active"])

        response = self.client.get(
            self.list_url,
            {"is_active": "false"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_guest_cannot_create(self):
        response = self.client.post(
            self.list_url,
            {
                "name_ar": "أنوا",
                "name_en": "ANUA",
                "slug": "anua",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_customer_cannot_update(self):
        self.authenticate(self.customer)

        response = self.client.patch(
            self.detail_url,
            {"is_active": False},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    

    def test_unfiltered_list_includes_active_and_inactive(self):
        self.authenticate(self.staff)

        self.brand.is_active = False
        self.brand.save(update_fields=["is_active"])

        active_brand = Brand.objects.create(
            name_ar="لاروش بوزيه",
            name_en="La Roche-Posay",
            slug="la-roche-posay",
            is_active=True,
        )

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)

        returned_ids = {
            item["id"]
            for item in response.data["results"]
        }

        self.assertEqual(
            returned_ids,
            {self.brand.pk, active_brand.pk},
        )

