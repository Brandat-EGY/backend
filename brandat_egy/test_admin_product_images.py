
from io import BytesIO
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from PIL import Image

from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Product, ProductImage


User = get_user_model()


class AdminProductImageCreateTests(APITestCase):

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
            name_en="Face Serum",
            description_ar="سيروم مرطب",
            is_available=False,
        )

        self.url = reverse(
            "admin-product-image-create",
            kwargs={"product_id": self.product.pk},
        )

        self.staff = User.objects.create_user(
            phone="01055555555",
            customer_name="Admin User",
            password="SecurePass2026!",
            is_staff=True,
        )

        self.customer = User.objects.create_user(
            phone="01066666666",
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

    def make_image(self, name="test.png", fmt="PNG"):
        buffer = BytesIO()

        image = Image.new(
            "RGB",
            (100, 100),
            color="white",
        )

        image.save(buffer, format=fmt)

        return SimpleUploadedFile(
            name,
            buffer.getvalue(),
            content_type="image/png",
        )

    def upload(self, name="test.png", is_main=None):
        data = {
            "image": self.make_image(name),
        }

        if is_main is not None:
            data["is_main"] = str(is_main).lower()

        return self.client.post(
            self.url,
            data,
            format="multipart",
        )

    def test_first_image_becomes_main(self):
        self.authenticate(self.staff)

        response = self.upload(
            name="first.png",
            is_main=False,
        )

        self.assertEqual(response.status_code, 201)

        image = ProductImage.objects.get(
            pk=response.data["id"]
        )

        self.assertTrue(image.is_main)
        self.assertTrue(
            response.data["image"].endswith(
                "/media/products/first.png"
            )
        )

    def test_second_image_is_not_main(self):
        self.authenticate(self.staff)

        self.upload("first.png")
        response = self.upload("second.png")

        self.assertEqual(response.status_code, 201)

        self.assertFalse(
            ProductImage.objects.get(
                pk=response.data["id"]
            ).is_main
        )

        self.assertEqual(
            ProductImage.objects.filter(
                product=self.product,
                is_main=True,
            ).count(),
            1,
        )

    def test_new_main_replaces_old_main(self):
        self.authenticate(self.staff)

        first = self.upload("first.png")
        second = self.upload(
            "second.png",
            is_main=True,
        )

        self.assertEqual(second.status_code, 201)

        self.assertFalse(
            ProductImage.objects.get(
                pk=first.data["id"]
            ).is_main
        )

        self.assertTrue(
            ProductImage.objects.get(
                pk=second.data["id"]
            ).is_main
        )

    def test_invalid_image_is_rejected(self):
        self.authenticate(self.staff)

        fake_image = SimpleUploadedFile(
            "fake.png",
            b"This is not an image",
            content_type="image/png",
        )

        response = self.client.post(
            self.url,
            {"image": fake_image},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("image", response.data)
        self.assertEqual(
            ProductImage.objects.count(),
            0,
        )

    def test_unsupported_format_is_rejected(self):
        self.authenticate(self.staff)

        image = self.make_image(
            "animated.gif",
            fmt="GIF",
        )

        response = self.client.post(
            self.url,
            {"image": image},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("image", response.data)

    def test_image_is_required(self):
        self.authenticate(self.staff)

        response = self.client.post(
            self.url,
            {},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("image", response.data)

    def test_guest_cannot_upload(self):
        response = self.upload()

        self.assertEqual(response.status_code, 401)
        self.assertFalse(
            ProductImage.objects.exists()
        )

    def test_customer_cannot_upload(self):
        self.authenticate(self.customer)

        response = self.upload()

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            ProductImage.objects.exists()
        )

    def test_product_not_found(self):
        self.authenticate(self.staff)

        url = reverse(
            "admin-product-image-create",
            kwargs={"product_id": 999999},
        )

        response = self.client.post(
            url,
            {"image": self.make_image()},
            format="multipart",
        )

        self.assertEqual(response.status_code, 404)

    def test_cannot_override_product(self):
        self.authenticate(self.staff)

        response = self.client.post(
            self.url,
            {
                "image": self.make_image(),
                "product": "999999",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("product", response.data)
        self.assertFalse(
            ProductImage.objects.exists()
        )
