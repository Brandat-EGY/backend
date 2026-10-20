from io import BytesIO
import tempfile
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.db import IntegrityError, transaction

from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Product, ProductImage


from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from PIL import Image



User = get_user_model()


class AdminProductImageSetMainTests(APITestCase):

    def setUp(self):
        self.product = Product.objects.create(
            name_ar="سيروم للبشرة",
            name_en="Face Serum",
            description_ar="سيروم مرطب",
            is_available=False,
        )

        self.first_image = ProductImage.objects.create(
            product=self.product,
            image="products/first.jpg",
            is_main=True,
        )

        self.second_image = ProductImage.objects.create(
            product=self.product,
            image="products/second.jpg",
            is_main=False,
        )

        self.url = reverse(
            "admin-product-image-set-main",
            kwargs={
                "product_id": self.product.pk,
                "image_id": self.second_image.pk,
            },
        )

        self.staff = User.objects.create_user(
            phone="01077777777",
            customer_name="Admin User",
            password="SecurePass2026!",
            is_staff=True,
        )

        self.customer = User.objects.create_user(
            phone="01099999999",
            customer_name="Customer",
            password="SecurePass2026!",
        )

    def authenticate(self, user):
        token = RefreshToken.for_user(user)

        self.client.credentials(
            HTTP_AUTHORIZATION=(
                f"Bearer {token.access_token}"
            )
        )

    def test_staff_can_change_main_image(self):
        self.authenticate(self.staff)

        response = self.client.patch(self.url)

        self.assertEqual(response.status_code, 200)

        self.first_image.refresh_from_db()
        self.second_image.refresh_from_db()

        self.assertFalse(self.first_image.is_main)
        self.assertTrue(self.second_image.is_main)

        self.assertTrue(response.data["is_main"])

    def test_only_one_main_image(self):
        self.authenticate(self.staff)

        self.client.patch(self.url)

        main_images_count = (
            ProductImage.objects.filter(
                product=self.product,
                is_main=True,
            ).count()
        )

        self.assertEqual(main_images_count, 1)

    def test_setting_same_main_twice(self):
        self.authenticate(self.staff)

        self.client.patch(self.url)
        response = self.client.patch(self.url)

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            ProductImage.objects.filter(
                product=self.product,
                is_main=True,
            ).count(),
            1,
        )

    def test_image_from_another_product_returns_404(self):
        self.authenticate(self.staff)

        another_product = Product.objects.create(
            name_ar="منتج آخر",
            description_ar="وصف آخر",
        )

        url = reverse(
            "admin-product-image-set-main",
            kwargs={
                "product_id": another_product.pk,
                "image_id": self.second_image.pk,
            },
        )

        response = self.client.patch(url)

        self.assertEqual(response.status_code, 404)

        self.first_image.refresh_from_db()
        self.assertTrue(self.first_image.is_main)

    def test_nonexistent_image_returns_404(self):
        self.authenticate(self.staff)

        url = reverse(
            "admin-product-image-set-main",
            kwargs={
                "product_id": self.product.pk,
                "image_id": 999999,
            },
        )

        response = self.client.patch(url)

        self.assertEqual(response.status_code, 404)

    def test_nonexistent_product_returns_404(self):
        self.authenticate(self.staff)

        url = reverse(
            "admin-product-image-set-main",
            kwargs={
                "product_id": 999999,
                "image_id": self.second_image.pk,
            },
        )

        response = self.client.patch(url)

        self.assertEqual(response.status_code, 404)

    def test_guest_cannot_change_main_image(self):
        response = self.client.patch(self.url)

        self.assertEqual(response.status_code, 401)

        self.first_image.refresh_from_db()
        self.assertTrue(self.first_image.is_main)

    def test_customer_cannot_change_main_image(self):
        self.authenticate(self.customer)

        response = self.client.patch(self.url)

        self.assertEqual(response.status_code, 403)

        self.first_image.refresh_from_db()
        self.assertTrue(self.first_image.is_main)


class AdminProductImageDeleteTests(APITestCase):

    def setUp(self):
        self.temp_media = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_media.cleanup)

        media_settings = override_settings(
            MEDIA_ROOT=self.temp_media.name,
            MEDIA_URL="/media/",
        )
        media_settings.enable()
        self.addCleanup(media_settings.disable)

        self.product = Product.objects.create(
            name_ar="سيروم للبشرة",
            description_ar="سيروم مرطب",
            is_available=False,
        )

        self.first = ProductImage.objects.create(
            product=self.product,
            image=self.make_image("first.png"),
            is_main=True,
        )

        self.second = ProductImage.objects.create(
            product=self.product,
            image=self.make_image("second.png"),
            is_main=False,
        )

        self.staff = User.objects.create_user(
            phone="01055554444",
            customer_name="Admin",
            password="SecurePass2026!",
            is_staff=True,
        )

        self.customer = User.objects.create_user(
            phone="01066663333",
            customer_name="Customer",
            password="SecurePass2026!",
        )

        self.url = self.image_url(self.first.pk)

    def make_image(self, filename):
        buffer = BytesIO()

        Image.new(
            "RGB",
            (20, 20),
            color="white",
        ).save(buffer, format="PNG")

        return SimpleUploadedFile(
            filename,
            buffer.getvalue(),
            content_type="image/png",
        )

    def image_url(self, image_id, product_id=None):
        return reverse(
            "admin-product-image-delete",
            kwargs={
                "product_id": product_id or self.product.pk,
                "image_id": image_id,
            },
        )

    def authenticate(self, user):
        token = RefreshToken.for_user(user)

        self.client.credentials(
            HTTP_AUTHORIZATION=(
                f"Bearer {token.access_token}"
            )
        )

    def test_delete_main_assigns_replacement(self):
        self.authenticate(self.staff)

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            ProductImage.objects.filter(
                pk=self.first.pk
            ).exists()
        )

        self.second.refresh_from_db()
        self.assertTrue(self.second.is_main)

    def test_delete_additional_preserves_main(self):
        self.authenticate(self.staff)

        response = self.client.delete(
            self.image_url(self.second.pk)
        )

        self.assertEqual(response.status_code, 204)

        self.first.refresh_from_db()
        self.assertTrue(self.first.is_main)

    def test_delete_last_draft_image(self):
        self.authenticate(self.staff)

        self.second.delete()

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, 204)

        self.assertFalse(
            ProductImage.objects.filter(
                product=self.product
            ).exists()
        )

    def test_cannot_delete_last_published_image(self):
        self.authenticate(self.staff)

        self.second.delete()

        self.product.is_available = True
        self.product.save(
            update_fields=["is_available"]
        )

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, 400)
        self.assertIn("image", response.data)

        self.assertTrue(
            ProductImage.objects.filter(
                pk=self.first.pk
            ).exists()
        )

    def test_file_deleted_after_commit(self):
        self.authenticate(self.staff)

        filename = self.first.image.name
        storage = self.first.image.storage

        self.assertTrue(storage.exists(filename))

        with self.captureOnCommitCallbacks(
            execute=True
        ) as callbacks:
            response = self.client.delete(self.url)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(len(callbacks), 1)
        self.assertFalse(storage.exists(filename))

    def test_shared_file_is_not_deleted(self):
        self.authenticate(self.staff)

        filename = self.first.image.name
        storage = self.first.image.storage

        other_product = Product.objects.create(
            name_ar="منتج آخر",
            description_ar="وصف آخر",
        )

        ProductImage.objects.create(
            product=other_product,
            image=filename,
            is_main=True,
        )

        with self.captureOnCommitCallbacks(
            execute=True
        ):
            response = self.client.delete(self.url)

        self.assertEqual(response.status_code, 204)
        self.assertTrue(storage.exists(filename))

    def test_image_from_other_product(self):
        self.authenticate(self.staff)

        other_product = Product.objects.create(
            name_ar="منتج آخر",
            description_ar="وصف آخر",
        )

        response = self.client.delete(
            self.image_url(
                self.first.pk,
                other_product.pk,
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_nonexistent_image(self):
        self.authenticate(self.staff)

        response = self.client.delete(
            self.image_url(999999)
        )

        self.assertEqual(response.status_code, 404)

    def test_repeated_delete_returns_404(self):
        self.authenticate(self.staff)

        first_response = self.client.delete(self.url)
        second_response = self.client.delete(self.url)

        self.assertEqual(first_response.status_code, 204)
        self.assertEqual(second_response.status_code, 404)

    def test_guest_cannot_delete(self):
        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, 401)

        self.assertTrue(
            ProductImage.objects.filter(
                pk=self.first.pk
            ).exists()
        )

    def test_customer_cannot_delete(self):
        self.authenticate(self.customer)

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, 403)

        self.assertTrue(
            ProductImage.objects.filter(
                pk=self.first.pk
            ).exists()
        )



class ProductMainImageConstraintTests(APITestCase):

    def setUp(self):
        self.product = Product.objects.create(
            name_ar="سيروم مرطب",
            description_ar="سيروم للبشرة",
        )

    def test_cannot_have_two_main_images(self):
        ProductImage.objects.create(
            product=self.product,
            image="products/first.jpg",
            is_main=True,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductImage.objects.create(
                    product=self.product,
                    image="products/second.jpg",
                    is_main=True,
                )

        self.assertEqual(
            ProductImage.objects.filter(
                product=self.product,
                is_main=True,
            ).count(),
            1,
        )

    def test_multiple_additional_images_allowed(self):
        for index in range(3):
            ProductImage.objects.create(
                product=self.product,
                image=f"products/image_{index}.jpg",
                is_main=False,
            )

        self.assertEqual(
            ProductImage.objects.filter(
                product=self.product,
            ).count(),
            3,
        )

    def test_different_products_can_have_main_images(self):
        another_product = Product.objects.create(
            name_ar="كريم مرطب",
            description_ar="كريم للبشرة",
        )

        ProductImage.objects.create(
            product=self.product,
            image="products/first.jpg",
            is_main=True,
        )

        ProductImage.objects.create(
            product=another_product,
            image="products/second.jpg",
            is_main=True,
        )

        self.assertEqual(
            ProductImage.objects.filter(
                is_main=True,
            ).count(),
            2,
        )
