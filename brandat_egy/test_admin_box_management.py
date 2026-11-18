
from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory

from PIL import Image

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.db import IntegrityError, transaction

from rest_framework.test import APITestCase

from .models import (
    Box,
    BoxItem,
    BoxImage,
    Product,
    ProductVariant,
)


User = get_user_model()


class AdminBoxManagementTests(APITestCase):

    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)

        media_settings = override_settings(
            MEDIA_ROOT=self.media_directory.name
        )
        media_settings.enable()
        self.addCleanup(media_settings.disable)

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

        self.product = Product.objects.create(
            name_ar="سيروم",
            description_ar="سيروم للعناية بالبشرة",
            is_available=True,
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            price=Decimal("200.00"),
            stock=10,
            is_active=True,
        )

        self.box = Box.objects.create(
            name_ar="بوكس العناية",
            description_ar="بوكس للعناية بالبشرة",
            sku="BOX-MANAGEMENT-001",
            price=Decimal("500.00"),
            stock=5,
            is_active=False,
        )

        self.item_url = reverse(
            "admin-box-item-create",
            kwargs={"box_id": self.box.pk},
        )

        self.image_url = reverse(
            "admin-box-image-create",
            kwargs={"box_id": self.box.pk},
        )

        self.publish_url = reverse(
            "admin-box-publish",
            kwargs={"box_id": self.box.pk},
        )

        self.unpublish_url = reverse(
            "admin-box-unpublish",
            kwargs={"box_id": self.box.pk},
        )

        self.client.force_authenticate(
            user=self.admin
        )

    def make_image(self, name="box.png"):
        buffer = BytesIO()

        Image.new(
            "RGB",
            (10, 10),
        ).save(buffer, format="PNG")

        return SimpleUploadedFile(
            name,
            buffer.getvalue(),
            content_type="image/png",
        )

    def add_item(self, quantity=2):
        return self.client.post(
            self.item_url,
            {
                "variant_id": self.variant.pk,
                "quantity": quantity,
            },
            format="json",
        )

    def upload_image(self):
        return self.client.post(
            self.image_url,
            {"image": self.make_image()},
            format="multipart",
        )

    def prepare_box(self):
        item_response = self.add_item()
        image_response = self.upload_image()

        self.assertEqual(item_response.status_code, 201)
        self.assertEqual(image_response.status_code, 201)

    def test_add_variant_to_box(self):
        response = self.add_item(quantity=2)

        self.assertEqual(response.status_code, 201)

        item = BoxItem.objects.get(box=self.box)

        self.assertEqual(item.variant, self.variant)
        self.assertEqual(item.quantity, 2)

    def test_duplicate_variant_is_rejected(self):
        self.add_item()

        response = self.add_item()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            BoxItem.objects.filter(box=self.box).count(),
            1,
        )

    def test_invalid_quantity_is_rejected(self):
        response = self.add_item(quantity=0)

        self.assertEqual(response.status_code, 400)

    def test_update_box_item_quantity(self):
        self.add_item()

        item = BoxItem.objects.get(box=self.box)

        url = reverse(
            "admin-box-item-detail",
            kwargs={
                "box_id": self.box.pk,
                "item_id": item.pk,
            },
        )

        response = self.client.patch(
            url,
            {"quantity": 3},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        item.refresh_from_db()
        self.assertEqual(item.quantity, 3)

    def test_delete_box_item(self):
        self.add_item()

        item = BoxItem.objects.get(box=self.box)

        url = reverse(
            "admin-box-item-detail",
            kwargs={
                "box_id": self.box.pk,
                "item_id": item.pk,
            },
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            BoxItem.objects.filter(pk=item.pk).exists()
        )

    def test_first_image_is_main(self):
        response = self.upload_image()

        self.assertEqual(response.status_code, 201)

        image = BoxImage.objects.get(box=self.box)

        self.assertTrue(image.is_main)

    def test_set_another_image_as_main(self):
        self.upload_image()
        self.upload_image()

        images = list(
            BoxImage.objects.filter(
                box=self.box
            ).order_by("pk")
        )

        second_image = images[1]

        url = reverse(
            "admin-box-image-set-main",
            kwargs={
                "box_id": self.box.pk,
                "image_id": second_image.pk,
            },
        )

        response = self.client.patch(
            url,
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            BoxImage.objects.filter(
                box=self.box,
                is_main=True,
            ).count(),
            1,
        )

        second_image.refresh_from_db()
        self.assertTrue(second_image.is_main)

    def test_publish_requires_items_and_image(self):
        response = self.client.post(self.publish_url)

        self.assertEqual(response.status_code, 400)

        self.box.refresh_from_db()
        self.assertFalse(self.box.is_active)

    def test_publish_successfully(self):
        self.prepare_box()

        response = self.client.post(self.publish_url)

        self.assertEqual(response.status_code, 200)

        self.box.refresh_from_db()
        self.assertTrue(self.box.is_active)

    def test_cannot_publish_with_low_variant_stock(self):
        self.prepare_box()

        self.variant.stock = 1
        self.variant.save(update_fields=["stock"])

        response = self.client.post(self.publish_url)

        self.assertEqual(response.status_code, 400)

        self.box.refresh_from_db()
        self.assertFalse(self.box.is_active)

    def test_cannot_edit_items_while_published(self):
        self.prepare_box()
        self.client.post(self.publish_url)

        item = BoxItem.objects.get(box=self.box)

        url = reverse(
            "admin-box-item-detail",
            kwargs={
                "box_id": self.box.pk,
                "item_id": item.pk,
            },
        )

        response = self.client.patch(
            url,
            {"quantity": 5},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

    def test_cannot_delete_last_published_image(self):
        self.prepare_box()
        self.client.post(self.publish_url)

        image = BoxImage.objects.get(box=self.box)

        url = reverse(
            "admin-box-image-delete",
            kwargs={
                "box_id": self.box.pk,
                "image_id": image.pk,
            },
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, 400)

        self.assertTrue(
            BoxImage.objects.filter(pk=image.pk).exists()
        )

    def test_unpublish_allows_editing_again(self):
        self.prepare_box()
        self.client.post(self.publish_url)

        response = self.client.post(
            self.unpublish_url
        )

        self.assertEqual(response.status_code, 200)

        self.box.refresh_from_db()
        self.assertFalse(self.box.is_active)

        item = BoxItem.objects.get(box=self.box)

        url = reverse(
            "admin-box-item-detail",
            kwargs={
                "box_id": self.box.pk,
                "item_id": item.pk,
            },
        )

        response = self.client.patch(
            url,
            {"quantity": 3},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

    def test_customer_cannot_manage_boxes(self):
        self.client.force_authenticate(
            user=self.customer
        )

        response = self.add_item()

        self.assertEqual(response.status_code, 403)
    


    def test_delete_main_image_promotes_another(self):
        self.upload_image()
        self.upload_image()

        images = list(
            BoxImage.objects.filter(
                box=self.box
            ).order_by("pk")
        )

        first_image = images[0]
        second_image = images[1]

        self.assertTrue(first_image.is_main)
        self.assertFalse(second_image.is_main)

        url = reverse(
            "admin-box-image-delete",
            kwargs={
                "box_id": self.box.pk,
                "image_id": first_image.pk,
            },
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, 204)

        self.assertFalse(
            BoxImage.objects.filter(
                pk=first_image.pk
            ).exists()
        )

        second_image.refresh_from_db()

        self.assertTrue(second_image.is_main)

        self.assertEqual(
            BoxImage.objects.filter(
                box=self.box,
                is_main=True,
            ).count(),
            1,
        )


    def test_can_delete_last_image_from_draft(self):
        self.upload_image()

        image = BoxImage.objects.get(
            box=self.box
        )

        url = reverse(
            "admin-box-image-delete",
            kwargs={
                "box_id": self.box.pk,
                "image_id": image.pk,
            },
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, 204)

        self.assertFalse(
            BoxImage.objects.filter(
                box=self.box
            ).exists()
        )



def test_database_prevents_duplicate_main_images(self):
    BoxImage.objects.create(
        box=self.box,
        image="boxes/first.jpg",
        is_main=True,
    )

    with self.assertRaises(IntegrityError):
        with transaction.atomic():
            BoxImage.objects.create(
                box=self.box,
                image="boxes/second.jpg",
                is_main=True,
            )

    self.assertEqual(
        BoxImage.objects.filter(
            box=self.box,
            is_main=True,
        ).count(),
        1,
    )
