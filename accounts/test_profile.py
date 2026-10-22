
from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken


User = get_user_model()


class CustomerProfileAPITests(APITestCase):

    def setUp(self):
        self.url = reverse("account-me")

        self.user = User.objects.create_user(
            phone="01011112222",
            customer_name="Old Name",
            email="old@example.com",
            password="SecurePass2026!",
        )

        access_token = RefreshToken.for_user(
            self.user
        ).access_token

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {access_token}"
        )

    def test_get_profile(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["customer_name"],
            "Old Name",
        )
        self.assertEqual(
            response.data["phone"],
            "01011112222",
        )

    def test_update_profile(self):
        response = self.client.patch(
            self.url,
            {
                "customer_name": "New Name",
                "email": "new@example.com",
                "address": "Nasr City, Cairo",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()

        self.assertEqual(
            self.user.customer_name,
            "New Name",
        )
        self.assertEqual(
            self.user.email,
            "new@example.com",
        )
        self.assertEqual(
            self.user.address,
            "Nasr City, Cairo",
        )

    def test_partial_update(self):
        response = self.client.patch(
            self.url,
            {"customer_name": "Updated Name"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()

        self.assertEqual(
            self.user.customer_name,
            "Updated Name",
        )
        self.assertEqual(
            self.user.email,
            "old@example.com",
        )

    def test_phone_cannot_be_updated(self):
        response = self.client.patch(
            self.url,
            {"phone": "01099998888"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

        self.user.refresh_from_db()
        self.assertEqual(
            self.user.phone,
            "01011112222",
        )

    def test_cannot_change_staff_permissions(self):
        response = self.client.patch(
            self.url,
            {"is_staff": True},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)

    def test_invalid_email_is_rejected(self):
        response = self.client.patch(
            self.url,
            {"email": "invalid-email"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_guest_cannot_access_profile(self):
        self.client.credentials()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 401)

    def test_put_is_not_allowed(self):
        response = self.client.put(
            self.url,
            {"customer_name": "New Name"},
            format="json",
        )

        self.assertEqual(response.status_code, 405)
