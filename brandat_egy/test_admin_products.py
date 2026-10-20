from datetime import timedelta
from django.utils import timezone


from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Product, Brand, Category, ProductVariant, ProductImage, DailyOffer
from decimal import Decimal


User = get_user_model()


class AdminProductCreateTests(APITestCase):

    def setUp(self):
        self.url = reverse("admin-product-create")

        self.staff = User.objects.create_user(
            phone="01011111111",
            customer_name="Admin User",
            password="SecurePass2026!",
            is_staff=True,
        )

        self.customer = User.objects.create_user(
            phone="01022222222",
            customer_name="Customer",
            password="SecurePass2026!",
        )

        self.brand = Brand.objects.create(
            name_ar="كوسركس",
            name_en="COSRX",
            slug="cosrx",
            is_active=True,
        )

        self.category = Category.objects.create(
            name_ar="العناية بالبشرة",
            name_en="Skincare",
            slug="skincare",
            is_active=True,
        )

        self.payload = {
            "name_ar": "سيروم مرطب",
            "name_en": "Hydrating Serum",
            "description_ar": "سيروم للبشرة",
            "description_en": "Hydrating face serum",
            "brand": self.brand.pk,
            "category": self.category.pk,
        }

    def authenticate(self, user):
        token = RefreshToken.for_user(user)

        self.client.credentials(
            HTTP_AUTHORIZATION=(
                f"Bearer {token.access_token}"
            )
        )

    def test_guest_cannot_create_product(self):
        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

        self.assertEqual(Product.objects.count(), 0)

    def test_customer_cannot_create_product(self):
        self.authenticate(self.customer)

        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.assertEqual(Product.objects.count(), 0)

    def test_staff_creates_draft_product(self):
        self.authenticate(self.staff)

        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        product = Product.objects.get(
            pk=response.data["id"]
        )

        self.assertEqual(
            product.name_ar,
            "سيروم مرطب",
        )

        self.assertEqual(
            product.brand_id,
            self.brand.pk,
        )

        self.assertFalse(product.is_available)
        self.assertFalse(response.data["is_available"])

        # Draft products must not appear in storefront.
        listing = self.client.get(
            reverse("product-list")
        )

        self.assertEqual(listing.data["count"], 0)

    def test_invalid_brand_is_rejected(self):
        self.authenticate(self.staff)

        data = {
            **self.payload,
            "brand": 999999,
        }

        response = self.client.post(
            self.url,
            data,
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("brand", response.data)
        self.assertEqual(Product.objects.count(), 0)

    def test_brand_and_category_are_optional(self):
        self.authenticate(self.staff)

        data = {
            "name_ar": "منتج تجريبي",
            "description_ar": "وصف المنتج",
        }

        response = self.client.post(
            self.url,
            data,
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.data["brand"])
        self.assertIsNone(response.data["category"])

    def test_cannot_publish_during_creation(self):
        self.authenticate(self.staff)

        data = {
            **self.payload,
            "is_available": True,
        }

        response = self.client.post(
            self.url,
            data,
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("is_available", response.data)
        self.assertEqual(Product.objects.count(), 0)

    def test_required_fields(self):
        self.authenticate(self.staff)

        response = self.client.post(
            self.url,
            {"name_en": "Missing required data"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("name_ar", response.data)
        self.assertIn("description_ar", response.data)


class AdminProductVariantCreateTests(APITestCase):

    def setUp(self):
        self.product = Product.objects.create(
            name_ar="سيروم مرطب",
            name_en="Hydrating Serum",
            description_ar="سيروم للبشرة",
            is_available=False,
        )

        self.url = reverse(
            "admin-product-variant-create",
            kwargs={"product_id": self.product.pk},
        )

        self.staff = User.objects.create_user(
            phone="01033333333",
            customer_name="Admin User",
            password="SecurePass2026!",
            is_staff=True,
        )

        self.customer = User.objects.create_user(
            phone="01044444444",
            customer_name="Customer",
            password="SecurePass2026!",
        )

        self.payload = {
            "size": "30ml",
            "price": "500.00",
            "discount_price": "450.00",
            "stock": 10,
        }

    def authenticate(self, user):
        token = RefreshToken.for_user(user)

        self.client.credentials(
            HTTP_AUTHORIZATION=(
                f"Bearer {token.access_token}"
            )
        )

    def test_staff_creates_variant(self):
        self.authenticate(self.staff)

        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(response.status_code, 201)

        variant = ProductVariant.objects.get(
            pk=response.data["id"]
        )

        self.assertEqual(
            variant.product_id,
            self.product.pk,
        )
        self.assertEqual(variant.sku, "SERUM-30ML")
        self.assertEqual(variant.stock, 10)
        self.assertTrue(variant.is_active)

    def test_optional_fields(self):
        self.authenticate(self.staff)

        response = self.client.post(
            self.url,
            {
                "sku": "SERUM-50ML",
                "price": "700.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["size"], "")
        self.assertEqual(response.data["shade_ar"], "")
        self.assertEqual(response.data["shade_en"], "")
        self.assertIsNone(
            response.data["discount_price"]
        )
        self.assertEqual(response.data["stock"], 0)

    def test_invalid_discount_price(self):
        self.authenticate(self.staff)

        response = self.client.post(
            self.url,
            {
                **self.payload,
                "discount_price": "600.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "discount_price",
            response.data,
        )
        self.assertFalse(
            ProductVariant.objects.exists()
        )

    def test_duplicate_sku_is_rejected(self):
        self.authenticate(self.staff)

        ProductVariant.objects.create(
            product=self.product,
            sku="SERUM-30ML",
            price=Decimal("500.00"),
        )

        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("sku", response.data)

    def test_sku_is_case_insensitive(self):
        self.authenticate(self.staff)

        ProductVariant.objects.create(
            product=self.product,
            sku="serum-30ml",
            price=Decimal("500.00"),
        )

        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("sku", response.data)

    def test_invalid_price(self):
        self.authenticate(self.staff)

        response = self.client.post(
            self.url,
            {
                **self.payload,
                "price": "-100.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("price", response.data)

    def test_invalid_stock(self):
        self.authenticate(self.staff)

        response = self.client.post(
            self.url,
            {
                **self.payload,
                "stock": -5,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("stock", response.data)

    def test_product_not_found(self):
        self.authenticate(self.staff)

        url = reverse(
            "admin-product-variant-create",
            kwargs={"product_id": 999999},
        )

        response = self.client.post(
            url,
            self.payload,
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_customer_cannot_create_variant(self):
        self.authenticate(self.customer)

        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            ProductVariant.objects.exists()
        )

    def test_guest_cannot_create_variant(self):
        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(
            ProductVariant.objects.exists()
        )

    def test_cannot_override_product(self):
        self.authenticate(self.staff)

        response = self.client.post(
            self.url,
            {
                **self.payload,
                "product": 999999,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("product", response.data)
        self.assertFalse(
            ProductVariant.objects.exists()
        )



class AdminProductUpdateTests(APITestCase):

    def setUp(self):
        self.product = Product.objects.create(
            name_ar="سيروم قديم",
            name_en="Old Serum",
            description_ar="الوصف القديم",
            description_en="Old description",
            is_available=False,
        )

        self.url = reverse(
            "admin-product-update",
            kwargs={"product_id": self.product.pk},
        )

        self.staff = User.objects.create_user(
            phone="01012345678",
            customer_name="Admin",
            password="SecurePass2026!",
            is_staff=True,
        )

        self.customer = User.objects.create_user(
            phone="01087654321",
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

    def test_staff_can_update_product(self):
        self.authenticate(self.staff)

        response = self.client.patch(
            self.url,
            {
                "name_ar": "سيروم جديد",
                "name_en": "New Serum",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.product.refresh_from_db()

        self.assertEqual(
            self.product.name_ar,
            "سيروم جديد",
        )

        self.assertEqual(
            self.product.name_en,
            "New Serum",
        )

        self.assertEqual(
            self.product.description_ar,
            "الوصف القديم",
        )

    def test_cannot_publish_using_update(self):
        self.authenticate(self.staff)

        response = self.client.patch(
            self.url,
            {"is_available": True},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("is_available", response.data)

        self.product.refresh_from_db()
        self.assertFalse(self.product.is_available)

    def test_cannot_update_unknown_fields(self):
        self.authenticate(self.staff)

        response = self.client.patch(
            self.url,
            {"variants": []},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("variants", response.data)

    def test_invalid_name_is_rejected(self):
        self.authenticate(self.staff)

        response = self.client.patch(
            self.url,
            {"name_ar": ""},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("name_ar", response.data)

    def test_product_not_found(self):
        self.authenticate(self.staff)

        url = reverse(
            "admin-product-update",
            kwargs={"product_id": 999999},
        )

        response = self.client.patch(
            url,
            {"name_ar": "اسم جديد"},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_guest_cannot_update(self):
        response = self.client.patch(
            self.url,
            {"name_ar": "اسم جديد"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_customer_cannot_update(self):
        self.authenticate(self.customer)

        response = self.client.patch(
            self.url,
            {"name_ar": "اسم جديد"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_put_is_not_allowed(self):
        self.authenticate(self.staff)

        response = self.client.put(
            self.url,
            {"name_ar": "اسم جديد"},
            format="json",
        )

        self.assertEqual(response.status_code, 405)


class AdminProductVariantUpdateTests(APITestCase):

    def setUp(self):
        self.product = Product.objects.create(
            name_ar="سيروم مرطب",
            description_ar="سيروم للبشرة",
            is_available=False,
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="30ml",
            price=Decimal("500.00"),
            discount_price=Decimal("400.00"),
            stock=10,
        )

        self.original_sku = self.variant.sku

        self.url = reverse(
            "admin-product-variant-update",
            kwargs={"variant_id": self.variant.pk},
        )

        self.staff = User.objects.create_user(
            phone="01012345987",
            customer_name="Admin",
            password="SecurePass2026!",
            is_staff=True,
        )

        self.customer = User.objects.create_user(
            phone="01098765432",
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

    def test_partial_update(self):
        self.authenticate(self.staff)

        response = self.client.patch(
            self.url,
            {"size": "50ml"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.variant.refresh_from_db()

        self.assertEqual(self.variant.size, "50ml")
        self.assertEqual(
            self.variant.price,
            Decimal("500.00"),
        )
        self.assertEqual(
            self.variant.sku,
            self.original_sku,
        )

    def test_cannot_set_price_below_discount(self):
        self.authenticate(self.staff)

        response = self.client.patch(
            self.url,
            {"price": "350.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("discount_price", response.data)

        self.variant.refresh_from_db()
        self.assertEqual(
            self.variant.price,
            Decimal("500.00"),
        )

    def test_update_price_and_discount_together(self):
        self.authenticate(self.staff)

        response = self.client.patch(
            self.url,
            {
                "price": "350.00",
                "discount_price": "300.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.variant.refresh_from_db()

        self.assertEqual(
            self.variant.price,
            Decimal("350.00"),
        )
        self.assertEqual(
            self.variant.discount_price,
            Decimal("300.00"),
        )

    def test_remove_discount(self):
        self.authenticate(self.staff)

        response = self.client.patch(
            self.url,
            {"discount_price": None},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.variant.refresh_from_db()
        self.assertIsNone(self.variant.discount_price)

    def test_update_stock_and_active_status(self):
        self.authenticate(self.staff)

        response = self.client.patch(
            self.url,
            {
                "stock": 0,
                "is_active": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.variant.refresh_from_db()

        self.assertEqual(self.variant.stock, 0)
        self.assertFalse(self.variant.is_active)

    def test_cannot_change_sku(self):
        self.authenticate(self.staff)

        response = self.client.patch(
            self.url,
            {"sku": "MANUAL-SKU"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("sku", response.data)

        self.variant.refresh_from_db()
        self.assertEqual(
            self.variant.sku,
            self.original_sku,
        )

    def test_cannot_change_product(self):
        self.authenticate(self.staff)

        response = self.client.patch(
            self.url,
            {"product": 999999},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("product", response.data)

    def test_invalid_stock(self):
        self.authenticate(self.staff)

        response = self.client.patch(
            self.url,
            {"stock": -5},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("stock", response.data)

    def test_variant_not_found(self):
        self.authenticate(self.staff)

        url = reverse(
            "admin-product-variant-update",
            kwargs={"variant_id": 999999},
        )

        response = self.client.patch(
            url,
            {"stock": 10},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_guest_cannot_update(self):
        response = self.client.patch(
            self.url,
            {"stock": 20},
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_customer_cannot_update(self):
        self.authenticate(self.customer)

        response = self.client.patch(
            self.url,
            {"stock": 20},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_put_not_allowed(self):
        self.authenticate(self.staff)

        response = self.client.put(
            self.url,
            {"stock": 20},
            format="json",
        )

        self.assertEqual(response.status_code, 405)


class AdminProductPublishTests(APITestCase):

    def setUp(self):
        self.product = Product.objects.create(
            name_ar="سيروم مرطب",
            name_en="Hydrating Serum",
            description_ar="سيروم للبشرة",
            is_available=False,
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            price=Decimal("500.00"),
            stock=10,
            is_active=True,
        )

        self.image = ProductImage.objects.create(
            product=self.product,
            image="products/serum.jpg",
            is_main=True,
        )

        self.publish_url = reverse(
            "admin-product-publish",
            kwargs={"product_id": self.product.pk},
        )

        self.unpublish_url = reverse(
            "admin-product-unpublish",
            kwargs={"product_id": self.product.pk},
        )

        self.staff = User.objects.create_user(
            phone="01012345001",
            customer_name="Admin",
            password="SecurePass2026!",
            is_staff=True,
        )

        self.customer = User.objects.create_user(
            phone="01012345002",
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

    def test_publish_valid_product(self):
        self.authenticate(self.staff)

        response = self.client.post(
            self.publish_url
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_available"])

        self.product.refresh_from_db()
        self.assertTrue(self.product.is_available)

    def test_cannot_publish_without_variant(self):
        self.authenticate(self.staff)

        self.variant.delete()

        response = self.client.post(
            self.publish_url
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("variants", response.data)

    def test_cannot_publish_inactive_variant(self):
        self.authenticate(self.staff)

        self.variant.is_active = False
        self.variant.save(
            update_fields=["is_active"]
        )

        response = self.client.post(
            self.publish_url
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("variants", response.data)

    def test_cannot_publish_out_of_stock(self):
        self.authenticate(self.staff)

        self.variant.stock = 0
        self.variant.save(
            update_fields=["stock"]
        )

        response = self.client.post(
            self.publish_url
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("variants", response.data)

    def test_cannot_publish_without_image(self):
        self.authenticate(self.staff)

        self.image.delete()

        response = self.client.post(
            self.publish_url
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("images", response.data)

    def test_cannot_publish_without_main_image(self):
        self.authenticate(self.staff)

        self.image.is_main = False
        self.image.save(
            update_fields=["is_main"]
        )

        response = self.client.post(
            self.publish_url
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("images", response.data)

    def test_publish_twice_is_safe(self):
        self.authenticate(self.staff)

        first = self.client.post(self.publish_url)
        second = self.client.post(self.publish_url)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

        self.product.refresh_from_db()
        self.assertTrue(self.product.is_available)

    def test_republish_after_stock_runs_out(self):
        self.authenticate(self.staff)

        self.client.post(self.publish_url)

        self.variant.stock = 0
        self.variant.save(update_fields=["stock"])

        response = self.client.post(
            self.publish_url
        )

        self.assertEqual(response.status_code, 200)

        self.product.refresh_from_db()
        self.assertTrue(self.product.is_available)

    def test_unpublish_product(self):
        self.authenticate(self.staff)

        self.client.post(self.publish_url)

        response = self.client.post(
            self.unpublish_url
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_available"])

        self.product.refresh_from_db()
        self.assertFalse(self.product.is_available)

    def test_unpublish_twice_is_safe(self):
        self.authenticate(self.staff)

        first = self.client.post(self.unpublish_url)
        second = self.client.post(self.unpublish_url)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

    def test_draft_hidden_from_storefront(self):
        response = self.client.get(
            reverse("product-list")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)

    def test_published_product_visible_in_storefront(self):
        self.authenticate(self.staff)

        self.client.post(self.publish_url)

        response = self.client.get(
            reverse("product-list")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_customer_cannot_publish(self):
        self.authenticate(self.customer)

        response = self.client.post(
            self.publish_url
        )

        self.assertEqual(response.status_code, 403)

        self.product.refresh_from_db()
        self.assertFalse(self.product.is_available)

    def test_guest_cannot_publish(self):
        response = self.client.post(
            self.publish_url
        )

        self.assertEqual(response.status_code, 401)

    def test_product_not_found(self):
        self.authenticate(self.staff)

        url = reverse(
            "admin-product-publish",
            kwargs={"product_id": 999999},
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 404)


class AdminProductListTests(APITestCase):

    def setUp(self):
        self.url = reverse(
            "admin-product-create"
        )

        self.staff = User.objects.create_user(
            phone="01070000001",
            customer_name="Admin",
            password="SecurePass2026!",
            is_staff=True,
        )

        self.customer = User.objects.create_user(
            phone="01070000002",
            customer_name="Customer",
            password="SecurePass2026!",
        )

        self.draft = Product.objects.create(
            name_ar="سيروم مرطب",
            name_en="Hydrating Serum",
            description_ar="سيروم للبشرة",
            scanned_code="123456789",
            is_available=False,
        )

        self.published = Product.objects.create(
            name_ar="كريم للعين",
            name_en="Eye Cream",
            description_ar="كريم للعناية بالعين",
            scanned_code="123456789",
            is_available=True,
        )

        self.variant = ProductVariant.objects.create(
            product=self.published,
            price=Decimal("300.00"),
            stock=5,
        )

    def authenticate(self, user):
        token = RefreshToken.for_user(user)

        self.client.credentials(
            HTTP_AUTHORIZATION=(
                f"Bearer {token.access_token}"
            )
        )

    def test_staff_sees_draft_and_published(self):
        self.authenticate(self.staff)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)

        ids = {
            item["id"]
            for item in response.data["results"]
        }

        self.assertEqual(
            ids,
            {self.draft.pk, self.published.pk},
        )

    def test_filter_draft(self):
        self.authenticate(self.staff)

        response = self.client.get(
            self.url,
            {"status": "draft"},
        )

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["id"],
            self.draft.pk,
        )

    def test_filter_published(self):
        self.authenticate(self.staff)

        response = self.client.get(
            self.url,
            {"status": "published"},
        )

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["id"],
            self.published.pk,
        )

    def test_duplicate_scanned_code_returns_both(self):
        self.authenticate(self.staff)

        response = self.client.get(
            self.url,
            {"scanned_code": "123456789"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)

    def test_search_by_product_name(self):
        self.authenticate(self.staff)

        response = self.client.get(
            self.url,
            {"search": "Hydrating"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["id"],
            self.draft.pk,
        )

    def test_price_and_variant_count(self):
        self.authenticate(self.staff)

        response = self.client.get(
            self.url,
            {"status": "published"},
        )

        product = response.data["results"][0]

        self.assertEqual(
            product["starting_price"],
            "300.00",
        )
        self.assertTrue(product["in_stock"])
        self.assertEqual(product["variants_count"], 1)

    def test_pagination(self):
        self.authenticate(self.staff)

        response = self.client.get(
            self.url,
            {"page_size": 1},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(
            len(response.data["results"]),
            1,
        )

        self.assertIsNotNone(
            response.data["next"]
        )

    def test_guest_cannot_list(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 401)

    def test_customer_cannot_list(self):
        self.authenticate(self.customer)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_post_still_creates_draft(self):
        self.authenticate(self.staff)

        response = self.client.post(
            self.url,
            {
                "name_ar": "منتج جديد",
                "description_ar": "وصف جديد",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)

        product = Product.objects.get(
            pk=response.data["id"]
        )

        self.assertFalse(product.is_available)



class AdminProductDetailTests(APITestCase):

    def setUp(self):
        self.product = Product.objects.create(
            name_ar="سيروم مرطب",
            name_en="Hydrating Serum",
            description_ar="سيروم للبشرة",
            scanned_code="123456789",
            is_available=False,
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="30ml",
            price=Decimal("500.00"),
            discount_price=Decimal("450.00"),
            stock=5,
            is_active=True,
        )

        self.inactive_variant = (
            ProductVariant.objects.create(
                product=self.product,
                size="50ml",
                price=Decimal("700.00"),
                stock=0,
                is_active=False,
            )
        )

        ProductImage.objects.create(
            product=self.product,
            image="products/main.jpg",
            is_main=True,
        )

        now = timezone.now()

        DailyOffer.objects.create(
            variant=self.variant,
            price=Decimal("380.00"),
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=1),
            is_active=True,
        )

        self.url = reverse(
            "admin-product-update",
            kwargs={"product_id": self.product.pk},
        )

        self.staff = User.objects.create_user(
            phone="01033332222",
            customer_name="Admin",
            password="SecurePass2026!",
            is_staff=True,
        )

        self.customer = User.objects.create_user(
            phone="01044443333",
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

    def test_staff_can_view_draft_product(self):
        self.authenticate(self.staff)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_available"])
        self.assertEqual(
            response.data["scanned_code"],
            "123456789",
        )

    def test_all_variants_are_visible(self):
        self.authenticate(self.staff)

        response = self.client.get(self.url)

        variants = response.data["variants"]

        self.assertEqual(len(variants), 2)
        self.assertEqual(
            response.data["variants_count"],
            2,
        )

        ids = {item["id"] for item in variants}

        self.assertEqual(
            ids,
            {
                self.variant.pk,
                self.inactive_variant.pk,
            },
        )

    def test_effective_variant_price(self):
        self.authenticate(self.staff)

        response = self.client.get(self.url)

        variant = next(
            item for item in response.data["variants"]
            if item["id"] == self.variant.pk
        )

        self.assertEqual(
            variant["final_price"],
            "380.00",
        )

        self.assertTrue(variant["is_active"])

        # Draft products are not purchasable.
        self.assertFalse(variant["can_purchase"])

    def test_main_image_is_returned(self):
        self.authenticate(self.staff)

        response = self.client.get(self.url)

        self.assertEqual(
            len(response.data["images"]),
            1,
        )

        self.assertTrue(
            response.data["images"][0]["is_main"]
        )

    def test_draft_hidden_from_public_detail(self):
        response = self.client.get(
            reverse(
                "product-detail",
                kwargs={"product_id": self.product.pk},
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_get_does_not_break_patch(self):
        self.authenticate(self.staff)

        response = self.client.patch(
            self.url,
            {"name_en": "Updated Serum"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.product.refresh_from_db()

        self.assertEqual(
            self.product.name_en,
            "Updated Serum",
        )

    def test_guest_cannot_view(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 401)

    def test_customer_cannot_view(self):
        self.authenticate(self.customer)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_nonexistent_product_returns_404(self):
        self.authenticate(self.staff)

        url = reverse(
            "admin-product-update",
            kwargs={"product_id": 999999},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)
