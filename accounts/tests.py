
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase


User = get_user_model()

TEST_PASSWORD = "SecurePass2026!"


class AuthenticationAPITests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone="01011111111",
            customer_name="Sara Ahmed",
            password=TEST_PASSWORD,
        )

        self.register_url = reverse("account-register")
        self.login_url = reverse("account-login")
        self.me_url = reverse("account-me")
        self.refresh_url = reverse("token_refresh")
        self.logout_url = reverse("account-logout")

    def register_data(self, **overrides):
        data = {
            "customer_name": "Fatma Ahmed",
            "phone": "01022222222",
            "email": "fatma@example.com",
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
        }

        data.update(overrides)
        return data

    def login(self):
        return self.client.post(
            self.login_url,
            {
                "phone": self.user.phone,
                "password": TEST_PASSWORD,
            },
            format="json",
        )

    # -------------------------
    # Register Tests
    # -------------------------

    def test_register_success(self):
        response = self.client.post(
            self.register_url,
            self.register_data(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        user = User.objects.get(
            phone="01022222222",
        )

        self.assertTrue(
            user.check_password(TEST_PASSWORD)
        )

        self.assertNotIn(
            "password",
            response.data["user"],
        )

    def test_register_duplicate_phone(self):
        response = self.client.post(
            self.register_url,
            self.register_data(phone=self.user.phone),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            User.objects.filter(
                phone=self.user.phone
            ).count(),
            1,
        )

    def test_register_password_mismatch(self):
        response = self.client.post(
            self.register_url,
            self.register_data(
                password_confirm="DifferentPass2026!"
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertIn(
            "password_confirm",
            response.data,
        )

    # -------------------------
    # Login Tests
    # -------------------------

    def test_login_success(self):
        response = self.login()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertIn("access", response.data["tokens"])
        self.assertIn("refresh", response.data["tokens"])

        self.assertEqual(
            response.data["user"]["id"],
            self.user.pk,
        )

    def test_login_wrong_password(self):
        response = self.client.post(
            self.login_url,
            {
                "phone": self.user.phone,
                "password": "WrongPassword123!",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

        self.assertNotIn("tokens", response.data)

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.login()

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    # -------------------------
    # JWT Authentication Tests
    # -------------------------

    def test_me_requires_authentication(self):
        response = self.client.get(self.me_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_me_with_access_token(self):
        login_response = self.login()

        access = login_response.data["tokens"]["access"]

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {access}"
        )

        response = self.client.get(self.me_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["id"],
            self.user.pk,
        )

    # -------------------------
    # Refresh Token Tests
    # -------------------------

    def test_refresh_rotation(self):
        login_response = self.login()

        old_refresh = login_response.data["tokens"]["refresh"]

        response = self.client.post(
            self.refresh_url,
            {"refresh": old_refresh},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

        self.assertNotEqual(
            old_refresh,
            response.data["refresh"],
        )

        # Old refresh must be blacklisted.
        retry_response = self.client.post(
            self.refresh_url,
            {"refresh": old_refresh},
            format="json",
        )

        self.assertEqual(
            retry_response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    # -------------------------
    # Logout Tests
    # -------------------------

    def test_logout_blacklists_refresh(self):
        login_response = self.login()

        access = login_response.data["tokens"]["access"]
        refresh = login_response.data["tokens"]["refresh"]

        logout_response = self.client.post(
            self.logout_url,
            {"refresh": refresh},
            format="json",
        )

        self.assertEqual(
            logout_response.status_code,
            status.HTTP_200_OK,
        )

        # Blacklisted refresh cannot be reused.
        refresh_response = self.client.post(
            self.refresh_url,
            {"refresh": refresh},
            format="json",
        )

        self.assertEqual(
            refresh_response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

        # Existing access remains valid until expiry.
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {access}"
        )

        me_response = self.client.get(self.me_url)

        self.assertEqual(
            me_response.status_code,
            status.HTTP_200_OK,
        )


class LoginCSRFTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone="01033333333",
            customer_name="Test Customer",
            password=TEST_PASSWORD,
        )

        self.client = Client(
            enforce_csrf_checks=True
        )

        self.login_url = reverse("account-login")
        self.csrf_url = reverse("csrf-token")

        self.credentials = {
            "phone": self.user.phone,
            "password": TEST_PASSWORD,
        }

    def test_login_without_csrf_is_rejected(self):
        response = self.client.post(
            self.login_url,
            self.credentials,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_login_with_csrf_succeeds(self):
        # Get CSRF cookie.
        response = self.client.get(self.csrf_url)

        self.assertEqual(response.status_code, 200)

        csrf_token = self.client.cookies["csrftoken"].value

        # Login using cookie + CSRF header.
        response = self.client.post(
            self.login_url,
            self.credentials,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("tokens", response.json())
