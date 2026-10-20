
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Favorite, Product
from .favorites import Favorites


User = get_user_model()

TEST_PASSWORD = "SecurePass2026!"


class FavoritesAPITests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone="01011111111",
            customer_name="Sara Ahmed",
            password=TEST_PASSWORD,
        )

        self.other_user = User.objects.create_user(
            phone="01022222222",
            customer_name="Fatma Ahmed",
            password=TEST_PASSWORD,
        )

        self.serum = Product.objects.create(
            name_ar="سيرم للبشرة",
            description_ar="سيرم للعناية بالبشرة",
        )

        self.cream = Product.objects.create(
            name_ar="كريم مرطب",
            description_ar="كريم لترطيب البشرة",
        )

        self.list_url = reverse("favorite-list")
        self.login_url = reverse("account-login")

    def detail_url(self, product):
        return reverse(
            "favorite-detail",
            kwargs={"product_id": product.pk},
        )

    def authenticate_user(self, user):
        refresh = RefreshToken.for_user(user)

        self.client.credentials(
            HTTP_AUTHORIZATION=(
                f"Bearer {refresh.access_token}"
            ),
        )

    def login_user(self, password=TEST_PASSWORD):
        return self.client.post(
            self.login_url,
            {
                "phone": self.user.phone,
                "password": password,
            },
            format="json",
        )

    # -----------------------------------
    # Anonymous Favorites
    # -----------------------------------

    def test_guest_add_list_and_remove(self):
        url = self.detail_url(self.serum)

        response = self.client.post(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertTrue(response.data["created"])

        self.assertIn(
            self.serum.pk,
            self.client.session[Favorites.SESSION_KEY],
        )

        response = self.client.get(self.list_url)

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["id"],
            self.serum.pk,
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["removed"])

        response = self.client.get(self.list_url)

        self.assertEqual(response.data["count"], 0)

    def test_guest_duplicate_favorite(self):
        url = self.detail_url(self.serum)

        self.client.post(url)
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["created"])

        self.assertEqual(
            len(
                self.client.session[
                    Favorites.SESSION_KEY
                ]
            ),
            1,
        )

    def test_guest_sessions_are_isolated(self):
        self.client.post(
            self.detail_url(self.serum)
        )

        another_guest = APIClient()

        response = another_guest.get(self.list_url)

        self.assertEqual(response.data["count"], 0)

    # -----------------------------------
    # Authenticated Favorites
    # -----------------------------------

    def test_authenticated_add_and_remove(self):
        self.authenticate_user(self.user)

        url = self.detail_url(self.serum)

        response = self.client.post(url)

        self.assertEqual(response.status_code, 201)

        self.assertTrue(
            Favorite.objects.filter(
                user=self.user,
                product=self.serum,
            ).exists()
        )

        response = self.client.delete(url)

        self.assertTrue(response.data["removed"])

        self.assertFalse(
            Favorite.objects.filter(
                user=self.user,
                product=self.serum,
            ).exists()
        )

    def test_users_have_separate_favorites(self):
        Favorite.objects.create(
            user=self.user,
            product=self.serum,
        )

        self.authenticate_user(self.other_user)

        response = self.client.get(self.list_url)

        self.assertEqual(response.data["count"], 0)

        self.authenticate_user(self.user)

        response = self.client.get(self.list_url)

        self.assertEqual(response.data["count"], 1)

    def test_missing_product_returns_404(self):
        url = reverse(
            "favorite-detail",
            kwargs={"product_id": 999999},
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 404)

    # -----------------------------------
    # Merge Guest Favorites
    # -----------------------------------

    def test_merge_guest_favorites_on_login(self):
        # Existing account favorite
        Favorite.objects.create(
            user=self.user,
            product=self.serum,
        )

        # Guest adds another product
        self.client.post(
            self.detail_url(self.cream)
        )

        response = self.login_user()

        self.assertEqual(response.status_code, 200)

        self.assertNotIn(
            Favorites.SESSION_KEY,
            self.client.session,
        )

        favorite_ids = set(
            Favorite.objects.filter(
                user=self.user,
            ).values_list("product_id", flat=True)
        )

        self.assertEqual(
            favorite_ids,
            {self.serum.pk, self.cream.pk},
        )

        access = response.data["tokens"]["access"]

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {access}"
        )

        response = self.client.get(self.list_url)

        self.assertEqual(response.data["count"], 2)

    def test_merge_does_not_duplicate_favorites(self):
        Favorite.objects.create(
            user=self.user,
            product=self.serum,
        )

        self.client.post(
            self.detail_url(self.serum)
        )

        response = self.login_user()

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            Favorite.objects.filter(
                user=self.user,
                product=self.serum,
            ).count(),
            1,
        )

    def test_failed_login_keeps_guest_favorites(self):
        self.client.post(
            self.detail_url(self.cream)
        )

        response = self.login_user(
            password="WrongPassword123!"
        )

        self.assertEqual(response.status_code, 401)

        self.assertIn(
            self.cream.pk,
            self.client.session[
                Favorites.SESSION_KEY
            ],
        )

        self.assertFalse(
            Favorite.objects.filter(
                user=self.user,
                product=self.cream,
            ).exists()
        )

class FavoritesCSRFTests(TestCase):

    def setUp(self):
        self.client = Client(
            enforce_csrf_checks=True
        )

        self.product = Product.objects.create(
            name_ar="كريم مرطب",
            description_ar="كريم لترطيب البشرة",
        )

        self.url = reverse(
            "favorite-detail",
            kwargs={"product_id": self.product.pk},
        )

        self.csrf_url = reverse("csrf-token")

    def test_guest_add_without_csrf_is_rejected(self):
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 403)

    def test_guest_add_with_csrf_succeeds(self):
        self.client.get(self.csrf_url)

        csrf_token = (
            self.client.cookies["csrftoken"].value
        )

        response = self.client.post(
            self.url,
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 201)

        self.assertIn(
            self.product.pk,
            self.client.session[
                Favorites.SESSION_KEY
            ],
        )

    def test_guest_delete_without_csrf_is_rejected(self):
        self.client.get(self.csrf_url)

        csrf_token = (
            self.client.cookies["csrftoken"].value
        )

        self.client.post(
            self.url,
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, 403)

        self.assertIn(
            self.product.pk,
            self.client.session[
                Favorites.SESSION_KEY
            ],
        )
