from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from brandat_egy.models import (
    Box,
    BoxItem,
    Brand,
    Category,
    Collection,
    DailyOffer,
    Favorite,
    Order,
    OrderBox,
    OrderBoxItem,
    OrderItem,
    Product,
    ProductVariant,
    Review,
    ShippingRate,
)

ADMIN_PHONE = "0123456789"
ADMIN_PASSWORD = "123"


class Command(BaseCommand):
    help = "Load dummy store data and the demo admin (0123456789 / 123)."

    @transaction.atomic
    def handle(self, *args, **options):
        admin = self._upsert_user(
            phone=ADMIN_PHONE,
            customer_name="مدير المتجر",
            password=ADMIN_PASSWORD,
            email="admin@brandat.local",
            is_staff=True,
            is_superuser=True,
        )
        sara = self._upsert_user(
            phone="01010000001",
            customer_name="سارة أحمد",
            password="123",
            email="sara@brandat.local",
            address="مدينة نصر، القاهرة",
        )
        mona = self._upsert_user(
            phone="01010000002",
            customer_name="منى حسن",
            password="123",
            email="mona@brandat.local",
            address="الدقي، الجيزة",
        )

        makeup = self._category("makeup", "مكياج", "Makeup")
        skincare = self._category("skincare", "عناية بالبشرة", "Skincare")
        fragrance = self._category("fragrance", "عطور", "Fragrance")

        brandat = self._brand("brandat", "براندات", "Brandat")
        noura = self._brand("noura", "نورة", "Noura")

        lipstick = self._product(
            code="DUMMY-LIP",
            name_ar="أحمر شفاه مطفي",
            name_en="Matte Lipstick",
            description_ar="أحمر شفاه مطفي ثابت طوال اليوم.",
            description_en="A matte lipstick that stays on all day.",
            category=makeup,
            brand=brandat,
        )
        moisturizer = self._product(
            code="DUMMY-MOIST",
            name_ar="كريم ترطيب يومي",
            name_en="Daily Moisturizer",
            description_ar="كريم خفيف يرطب البشرة دون لمعان.",
            description_en="A light cream that hydrates without shine.",
            category=skincare,
            brand=noura,
        )
        musk = self._product(
            code="DUMMY-MUSK",
            name_ar="عطر مسك",
            name_en="Musk Perfume",
            description_ar="عطر مسك هادي مناسب للاستخدام اليومي.",
            description_en="A soft musk for everyday wear.",
            category=fragrance,
            brand=brandat,
        )

        lip_rose = self._variant(
            lipstick,
            sku="DUMMY-LIP-ROSE",
            shade_ar="وردي",
            shade_en="Rose",
            price="350.00",
            discount_price="299.00",
            stock=40,
        )
        lip_nude = self._variant(
            lipstick,
            sku="DUMMY-LIP-NUDE",
            shade_ar="نود",
            shade_en="Nude",
            price="350.00",
            stock=25,
        )
        moist = self._variant(
            moisturizer,
            sku="DUMMY-MOIST-50",
            size="50ml",
            price="420.00",
            discount_price="360.00",
            stock=30,
        )
        musk_bottle = self._variant(
            musk,
            sku="DUMMY-MUSK-50",
            size="50ml",
            price="890.00",
            stock=12,
        )

        box = self._box()
        BoxItem.objects.get_or_create(
            box=box,
            variant=lip_rose,
            defaults={"quantity": 1},
        )
        BoxItem.objects.get_or_create(
            box=box,
            variant=moist,
            defaults={"quantity": 1},
        )

        collection, _ = Collection.objects.get_or_create(
            slug="best-sellers",
            defaults={
                "name_ar": "الأكثر مبيعا",
                "name_en": "Best sellers",
                "description_ar": "اختيارات المتجر الأكثر طلبا.",
                "description_en": "The store's most requested picks.",
                "is_active": True,
            },
        )
        collection.boxes.add(box)

        now = timezone.now()
        offer, _ = DailyOffer.objects.get_or_create(
            variant=lip_nude,
            defaults={
                "price": Decimal("250.00"),
                "starts_at": now - timedelta(days=1),
                "ends_at": now + timedelta(days=14),
                "is_active": True,
            },
        )
        offer.price = Decimal("250.00")
        offer.starts_at = now - timedelta(days=1)
        offer.ends_at = now + timedelta(days=14)
        offer.is_active = True
        offer.box = None
        offer.full_clean()
        offer.save()

        self._shipping_fees()
        cairo = ShippingRate.objects.filter(name_ar="القاهرة").first()
        giza = ShippingRate.objects.filter(name_ar="الجيزة").first()

        confirmed = self._order(
            email="seed-order-confirmed@brandat.local",
            user=sara,
            customer_name=sara.customer_name,
            phone=sara.phone,
            address=sara.address,
            governorate=cairo,
            shipping_fee="45.00",
            status="confirmed",
        )
        self._order_item(confirmed, lip_rose, 2, "299.00")

        preparing = self._order(
            email="seed-order-preparing@brandat.local",
            user=mona,
            customer_name=mona.customer_name,
            phone=mona.phone,
            address=mona.address,
            governorate=giza,
            shipping_fee="55.00",
            status="preparing",
        )
        self._order_box(preparing, box, 1, "799.00")

        delivered = self._order(
            email="seed-order-delivered@brandat.local",
            user=sara,
            customer_name=sara.customer_name,
            phone=sara.phone,
            address=sara.address,
            governorate=cairo,
            shipping_fee="45.00",
            status="delivered",
        )
        delivered_item = self._order_item(delivered, moist, 1, "360.00")
        if delivered_item is not None and not hasattr(delivered_item, "review"):
            Review.objects.create(
                order_item=delivered_item,
                name=sara.customer_name,
                rating=5,
                comment="الترطيب خفيف والريحة هادية.",
            )

        self._order(
            email="seed-order-cancelled@brandat.local",
            user=None,
            customer_name="ليلى محمود",
            phone="01010000003",
            address="سموحة، الإسكندرية",
            governorate=ShippingRate.objects.filter(name_ar="الإسكندرية").first(),
            shipping_fee="70.00",
            status="cancelled",
        )
        cancelled = Order.objects.get(email="seed-order-cancelled@brandat.local")
        self._order_item(cancelled, musk_bottle, 1, "890.00")

        Favorite.objects.get_or_create(user=sara, product=lipstick)
        Favorite.objects.get_or_create(user=mona, product=musk)

        self.stdout.write(self.style.SUCCESS(
            f"Dummy data ready. Admin phone {admin.phone} / password {ADMIN_PASSWORD}"
        ))

    def _upsert_user(self, *, phone, customer_name, password, email="", address="", is_staff=False, is_superuser=False):
        user = User.objects.filter(phone=phone).first()
        if user is None:
            user = User(phone=phone)
        user.customer_name = customer_name
        user.email = email
        user.address = address
        user.is_staff = is_staff
        user.is_superuser = is_superuser
        user.is_active = True
        user.set_password(password)
        user.save()
        return user

    def _category(self, slug, name_ar, name_en):
        category, _ = Category.objects.get_or_create(
            slug=slug,
            defaults={"name_ar": name_ar, "name_en": name_en, "is_active": True},
        )
        return category

    def _brand(self, slug, name_ar, name_en):
        brand, _ = Brand.objects.get_or_create(
            slug=slug,
            defaults={"name_ar": name_ar, "name_en": name_en, "is_active": True},
        )
        return brand

    def _product(self, *, code, name_ar, name_en, description_ar, description_en, category, brand):
        product, _ = Product.objects.get_or_create(
            scanned_code=code,
            defaults={
                "name_ar": name_ar,
                "name_en": name_en,
                "description_ar": description_ar,
                "description_en": description_en,
                "category": category,
                "brand": brand,
                "is_available": True,
            },
        )
        return product

    def _variant(self, product, *, sku, price, stock, shade_ar="", shade_en="", size="", discount_price=None):
        variant, _ = ProductVariant.objects.get_or_create(
            sku=sku,
            defaults={
                "product": product,
                "shade_ar": shade_ar,
                "shade_en": shade_en,
                "size": size,
                "price": Decimal(price),
                "discount_price": Decimal(discount_price) if discount_price else None,
                "stock": stock,
                "is_active": True,
            },
        )
        return variant

    def _box(self):
        box, _ = Box.objects.get_or_create(
            sku="DUMMY-BOX-GLOW",
            defaults={
                "name_ar": "بوكس الإطلالة",
                "name_en": "Glow Box",
                "description_ar": "أحمر شفاه وكريم ترطيب في بوكس واحد.",
                "description_en": "A lipstick and a moisturizer in one box.",
                "price": Decimal("999.00"),
                "discount_price": Decimal("799.00"),
                "stock": 15,
                "is_active": True,
            },
        )
        return box

    def _shipping_fees(self):
        fees = {
            "القاهرة": "45.00",
            "الجيزة": "55.00",
            "الإسكندرية": "70.00",
        }
        for name, fee in fees.items():
            ShippingRate.objects.filter(name_ar=name).update(fee=Decimal(fee), is_active=True)

    def _order(self, *, email, user, customer_name, phone, address, governorate, shipping_fee, status):
        order = Order.objects.filter(email=email).first()
        if order is not None:
            return order
        return Order.objects.create(
            user=user,
            customer_name=customer_name,
            phone=phone,
            email=email,
            address=address,
            governorate=governorate,
            shipping_fee=Decimal(shipping_fee),
            status=status,
        )

    def _order_item(self, order, variant, quantity, price):
        item = order.items.filter(variant=variant).first()
        if item is not None:
            return item
        return OrderItem.objects.create(
            order=order,
            variant=variant,
            quantity=quantity,
            price=Decimal(price),
        )

    def _order_box(self, order, box, quantity, price):
        order_box = order.boxes.filter(box=box).first()
        if order_box is not None:
            return order_box
        order_box = OrderBox.objects.create(
            order=order,
            box=box,
            name_ar=box.name_ar,
            name_en=box.name_en,
            sku=box.sku,
            quantity=quantity,
            price=Decimal(price),
        )
        for item in box.items.select_related("variant__product"):
            OrderBoxItem.objects.create(
                order_box=order_box,
                variant=item.variant,
                sku=item.variant.sku,
                product_name_ar=item.variant.product.name_ar,
                product_name_en=item.variant.product.name_en,
                quantity=item.quantity,
            )
        return order_box
