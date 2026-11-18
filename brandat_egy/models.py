from django.db import models
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError

from .pricing import get_effective_price
from .sku import generate_variant_sku

# Create your models here.

class Category(models.Model):
    name_ar = models.CharField(_("Category Arabic name"), max_length=150)
    name_en = models.CharField(_("Category English name"), max_length=150)

    slug = models.SlugField(_("slug"), max_length=160, unique=True)

    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="children",
        null=True,
        blank=True,
        verbose_name=_("Parent category"),
    )

    is_active = models.BooleanField(_("Category is shown"), default=True)

    class Meta:
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")

    def __str__(self):
        return self.name_ar


class Brand(models.Model):
    name_ar = models.CharField(_("Brand Arabic name"), max_length=150)
    name_en = models.CharField(_("Brand English name"), max_length=150)

    slug = models.SlugField(_("slug"), max_length=160, unique=True)

    is_active = models.BooleanField(_("Brand is shown"), default=True)

    class Meta:
        verbose_name = _("Brand")
        verbose_name_plural = _("Brands")


    def __str__(self):
        return self.name_en

class Product(models.Model):
    name_ar = models.CharField(_("Product Arabic name"), max_length=200)
    name_en = models.CharField(_("Product English name"), max_length=200, blank=True)

    description_ar = models.TextField(_("Product Arabic description"),)
    description_en = models.TextField(_("Product English description"), blank=True)

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        null=True,
        blank=True,
        verbose_name=_("Category"),
    )

    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name="products",
        null=True,
        blank=True,
        verbose_name=_("Brand"),
    )

    scanned_code = models.CharField(
        _("Barcode"),
        max_length=512,
        null=True,
        blank=True,
    )

    is_available = models.BooleanField(_("Available for sale"), default=True)

    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)


    class Meta:
        verbose_name = _("Product")
        verbose_name_plural = _("Products")

    def __str__(self):
        return self.name_ar
    

    @property
    def main_image(self):
        return (
            self.images.filter(is_main=True).first()
            or self.images.first()
        )
    

    @property
    def average_rating(self):
        return (
            OrderItem.objects.filter(
                variant__product=self,
                review__isnull=False
            ).aggregate(
                average=models.Avg("review__rating")
            )["average"]
            or 0
        )
    
    @property
    def reviews_count(self):
        return OrderItem.objects.filter(
            variant__product=self,
            review__isnull=False
        ).count()

    @property
    def stock_total(self):
        return sum(variant.stock for variant in self.variants.all())

    @property
    def lowest_price(self):
        prices = [
            variant.price
            for variant in self.variants.all()
            if variant.is_active and variant.price is not None
        ]
        if not prices:
            return None
        return min(prices)

class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="variants",
        verbose_name=_("Product"),
    )

    size = models.CharField(_("Size"), max_length=100, blank=True)
    shade_ar = models.CharField(_("Shade Arabic name"), max_length=100, blank=True)
    shade_en = models.CharField(_("Shade English name"), max_length=100, blank=True)

    price = models.DecimalField(
        _("Variant price"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    discount_price = models.DecimalField(
        _("Discount price"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    sku = models.CharField(
        _("Variant code"),
        max_length=100,
        unique=True,
        default=generate_variant_sku,
        editable=False,
    )

    stock = models.PositiveIntegerField(_("Variant stock"), default=0)
    is_active = models.BooleanField(_("Variant is active"), default=True)

    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    class Meta:
        verbose_name = _("Product Variant")
        verbose_name_plural = _("Product Variants")

    def __str__(self):
        return f"{self.product.name_ar} - {self.sku}"

    def clean(self):
        super().clean()

        if (
            self.discount_price is not None
            and self.price is not None
            and self.discount_price >= self.price
        ):
            raise ValidationError({
                "discount_price": _(
                    "Discount price must be lower than the price."
                )
            })

    @property
    def final_price(self):
        return get_effective_price(self)


    @property
    def can_purchase(self):
        return (
            self.is_active
            and self.product.is_available
            and self.stock > 0
        )

class Box(models.Model):
    name_ar = models.CharField(_("Box Arabic name"), max_length=200)
    name_en = models.CharField(_("Box English name"), max_length=200, blank=True)

    description_ar = models.TextField(_("Box Arabic description"),)
    description_en = models.TextField(_("Box English description"), blank=True)

    sku = models.CharField(_("Box code"), max_length=100, unique=True)

    price = models.DecimalField(
        _("Box price"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    discount_price = models.DecimalField(
        _("Discount price"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    stock = models.PositiveIntegerField(_("Box stock"), default=0)
    is_active = models.BooleanField(_("Box is shown"), default=True)

    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    class Meta:
        verbose_name = _("Box")
        verbose_name_plural = _("Boxes")

    def __str__(self):
        return self.name_ar
    
    
    def clean(self):
        super().clean()

        if (self.discount_price is not None and self.price is not None and self.discount_price >= self.price):
            raise ValidationError({
                "discount_price": _("Discount price must be lower than the price.")
            })
        
    @property
    def final_price(self):
        return get_effective_price(self)
    
    @property
    def main_image(self):
        return (
            self.images.filter(is_main=True).first()
            or self.images.first()
        )
    
    @property
    def available_stock(self):
        if not self.is_active or self.stock <= 0:
            return 0

        items = list(
            self.items.select_related("variant__product")
        )

        if not items:
            return 0

        available = self.stock

        for item in items:
            variant = item.variant

            if not variant.can_purchase:
                return 0

            possible_boxes = variant.stock // item.quantity
            available = min(available, possible_boxes)

        return available

    @property
    def can_purchase(self):
        return self.available_stock > 0

class BoxItem(models.Model):
    box = models.ForeignKey(
        Box,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Box"),
    )

    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="box_items",
        verbose_name=_("Included product"),
    )

    quantity = models.PositiveIntegerField(
        _("Quantity"),
        default=1,
        validators=[MinValueValidator(1)],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["box", "variant"],
                name="unique_variant_per_box",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="box_item_quantity_at_least_one",
            ),
        ]
        verbose_name = _("Box Item")
        verbose_name_plural = _("Box Items")

    def __str__(self):
        return f"{self.box} - {self.variant} x {self.quantity}"


class BoxImage(models.Model):
    box = models.ForeignKey(
        Box,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("Box"),
    )

    image = models.ImageField(
        _("Image"),
        upload_to="boxes/",
    )

    is_main = models.BooleanField(
        _("Main image"),
        default=False,
    )

    created_at = models.DateTimeField(
        _("Image uploaded at"),
        auto_now_add=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["box"],
                condition=models.Q(is_main=True),
                name="unique_main_image_per_box",
                violation_error_message=_(
                    "This box already has a main photo. Turn that one off before choosing another."
                ),
            ),
        ]

        verbose_name = _("Box Image")
        verbose_name_plural = _("Box Images")


    def __str__(self):
        return self.box.name_ar

class Collection(models.Model):
    name_ar = models.CharField(_("Collection Arabic name"), max_length=200)
    name_en = models.CharField(_("Collection English name"), max_length=200, blank=True)

    description_ar = models.TextField(_("Collection Arabic description"), blank=True)
    description_en = models.TextField(_("Collection English description"), blank=True)

    slug = models.SlugField(_("slug"), max_length=200, unique=True)

    boxes = models.ManyToManyField(
        Box,
        related_name="collections",
        blank=True,
        verbose_name=_("Boxes"),
    )

    is_active = models.BooleanField(_("Collection is shown"), default=True)
    class Meta:
        verbose_name = _("Collection")
        verbose_name_plural = _("Collections")
    def __str__(self):
        return self.name_ar

class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("Product"),
    )
    image = models.ImageField(
        _("Image"),
        upload_to="products/",
    )
    is_main = models.BooleanField(_("Main image"), default=False)

    created_at = models.DateTimeField(_("Image uploaded at"), auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_main=True),
                name="unique_main_image_per_product",
                violation_error_message=_(
                    "This product already has a main photo. Turn that one off before choosing another."
                ),
            ),
        ]
        verbose_name = _("Product Image")
        verbose_name_plural = _("Product Images")


    def __str__(self):
        return _("Image of %(name)s") % {"name": self.product.name_ar}

class ShippingRate(models.Model):
    name_ar = models.CharField(_("Governorate"), max_length=100, unique=True)
    fee = models.DecimalField(
        _("Shipping fee"),
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    is_active = models.BooleanField(_("Shown at checkout"), default=True)

    class Meta:
        ordering = ["name_ar"]
        verbose_name = _("Shipping rate")
        verbose_name_plural = _("Shipping rates")

    def __str__(self):
        return self.name_ar


class Order(models.Model):

    STATUS_CHOICES = [
        ("confirmed", _("Confirmed")),
        ("preparing", _("Preparing")),
        ("shipped", _("Shipped")),
        ("delivered", _("Delivered")),
        ("cancelled", _("Cancelled")),
        ("pending", _("Pending")),
        ("paid", _("Paid")),
    ]


    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="orders",
        null=True,
        blank=True,
        verbose_name=_("Customer"),
    )

    session_key = models.CharField(
        _("Guest session"),
        max_length=40,
        null=True,
        blank=True,
    )

    customer_name = models.CharField(_("Customer name"), max_length=150)
    phone = models.CharField(_("Phone"), max_length=20)
    email = models.EmailField(
        _("Email"),
        blank=True,
    )

    address = models.TextField(_("Address"))

    governorate = models.ForeignKey(
        ShippingRate,
        on_delete=models.PROTECT,
        related_name="orders",
        null=True,
        blank=True,
        verbose_name=_("Governorate"),
    )

    shipping_fee = models.DecimalField(
        _("Shipping fee"),
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    status = models.CharField(
        _("Order status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default="confirmed",
    )

    stock_restored_at = models.DateTimeField(
        _("Stock restored at"),
        null=True,
        blank=True,
        editable=False,
    )

    created_at = models.DateTimeField(
        _("Order created at"),
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        _("Order updated at"),
        auto_now=True,
    )

    @property
    def total_price(self):
        products_total = sum(
            (item.total_price for item in self.items.all()),
            Decimal("0.00"),
        )
        boxes_total = sum(
            (box.total_price for box in self.boxes.all()),
            Decimal("0.00"),
        )

        return products_total + boxes_total + (self.shipping_fee or Decimal("0.00"))

    total_price.fget.short_description = _("Order total")

    class Meta:
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")
    @property
    def is_guest(self):
        return self.user is None

    def __str__(self):
        return _("Order %(number)s — %(name)s") % {
            "number": self.id,
            "name": self.customer_name,
        }

class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Order"),
    )

    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="order_items",
        verbose_name=_("Ordered variant"),
    )

    quantity = models.PositiveIntegerField(
        _("Quantity"),
        default=1,
        validators=[
            MinValueValidator(1),
        ],
    )

    price = models.DecimalField(
        _("Unit price"),
        max_digits=10,
        decimal_places=2,
    )

    class Meta:
        verbose_name = _("Order Item")
        verbose_name_plural = _("Order Items")

    @property
    def total_price(self):
        return self.price * self.quantity
    
    @property
    def product(self):
        return self.variant.product
        
    
    def __str__(self):
        return f"{self.variant} x {self.quantity}"
    


class OrderBox(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="boxes",
        verbose_name=_("Order"),
    )
    box = models.ForeignKey(
        Box,
        on_delete=models.PROTECT,
        related_name="order_boxes",
        verbose_name=_("Box"),
    )
    name_ar = models.CharField(_("Box Arabic name"), max_length=200)
    name_en = models.CharField(_("Box English name"), max_length=200, blank=True)
    sku = models.CharField(_("Box code"), max_length=100)

    quantity = models.PositiveIntegerField(
        _("Quantity"),
        default=1,
        validators=[MinValueValidator(1)],
    )
    price = models.DecimalField(
        _("Order box price"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    class Meta:
        verbose_name = _("Order Box")
        verbose_name_plural = _("Order Boxes")

    @property
    def total_price(self):
        return self.price * self.quantity

    total_price.fget.short_description = _("Line total")

    def __str__(self):
        return f"{self.name_ar} x {self.quantity}"


class OrderBoxItem(models.Model):
    order_box = models.ForeignKey(
        OrderBox,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Order Box"),
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="order_box_items",
        verbose_name=_("Packed product"),
    )
    sku = models.CharField(_("Item code"), max_length=100)
    product_name_ar = models.CharField(_("Product Arabic name"), max_length=200)
    product_name_en = models.CharField(_("Product English name"), max_length=200, blank=True)

    quantity = models.PositiveIntegerField(
        _("Quantity"),
        validators=[MinValueValidator(1)],
    )
    class Meta:
        verbose_name = _("Order Box Item")
        verbose_name_plural = _("Order Box Items")

    def __str__(self):
        return f"{self.sku} x {self.quantity}"
    

class DailyOffer(models.Model):
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="daily_offers",
        null=True,
        blank=True,
        verbose_name=_("Offer variant"),
    )
    box = models.ForeignKey(
        Box,
        on_delete=models.PROTECT,
        related_name="daily_offers",
        null=True,
        blank=True,
        verbose_name=_("Box"),
    )

    price = models.DecimalField(
        _("Offer price"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    starts_at = models.DateTimeField(_("Offer starts at"))
    ends_at = models.DateTimeField(_("Offer ends at"))
    is_active = models.BooleanField(_("Offer is active"), default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(variant__isnull=False, box__isnull=True)
                    | models.Q(variant__isnull=True, box__isnull=False)
                ),
                name="daily_offer_exactly_one_target",
            ),
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="daily_offer_end_after_start",
            ),
        ]

        verbose_name = _("Daily Offer")
        verbose_name_plural = _("Daily Offers")

    def clean(self):
        super().clean()

        if self.variant_id and self.box_id:
            message = _(
                "Leave one empty. The offer can be on a product option or a box, not both."
            )
            raise ValidationError({"variant": message, "box": message})

        if self.variant_id is None and self.box_id is None:
            message = _("Choose either a variant or a box.")
            raise ValidationError({"variant": message, "box": message})

        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.ends_at <= self.starts_at
        ):
            raise ValidationError({
                "ends_at": _("End time must be after start time.")
            })

        target = self.variant if self.variant_id else self.box

        if (
            target is not None
            and self.price is not None
            and self.price >= target.price
        ):
            raise ValidationError({
                "price": _(
                    "Offer price must be lower than the regular price."
                )
            })

        if (
            self.is_active
            and self.starts_at is not None
            and self.ends_at is not None
            and self.ends_at > self.starts_at
        ):
            overlapping_offers = DailyOffer.objects.filter(
                is_active=True,
                starts_at__lt=self.ends_at,
                ends_at__gt=self.starts_at,
            )
            if self.variant_id is not None:
                overlapping_offers = overlapping_offers.filter(
                    variant_id=self.variant_id,
                )
            else:
                overlapping_offers = overlapping_offers.filter(
                    box_id=self.box_id,
                )
            if self.pk is not None:
                overlapping_offers = overlapping_offers.exclude(pk=self.pk)
            if overlapping_offers.exists():
                raise ValidationError(
                    _(
                        "An active offer already overlaps this period "
                        "for the same item."
                    )
                )

    @property
    def discount_percent(self):
        target = self.variant or self.box
        regular = getattr(target, "price", None)
        if not regular:
            return 0
        return round((regular - self.price) / regular * 100)

    def offer_status(self):
        now = timezone.now()
        if not self.is_active:
            return "stopped"
        if self.starts_at and self.starts_at > now:
            return "scheduled"
        if self.ends_at and self.ends_at <= now:
            return "ended"
        return "running"

    def __str__(self):
        if self.variant_id:
            return gettext("Offer for %(item)s") % {"item": self.variant}
        if self.box_id:
            return gettext("Offer for %(item)s") % {"item": self.box}
        return gettext("Daily offer")

class Review(models.Model):
    order_item = models.OneToOneField(
        OrderItem,
        on_delete=models.CASCADE,
        related_name="review",
        null=True,
        blank=True,
        verbose_name=_("Reviewed item"),
    )
    order_box = models.OneToOneField(
        OrderBox,
        on_delete=models.CASCADE,
        related_name="review",
        null=True,
        blank=True,
        verbose_name=_("Reviewed box"),
    )
    name = models.CharField(
        _("Reviewer name"),
        max_length=100,
        blank=True,
    )

    rating = models.PositiveSmallIntegerField(
        _("Rating"),
        validators=[
            MinValueValidator(1),
            MaxValueValidator(5),
        ]
    )

    comment = models.TextField(
        _("Comment"),
        blank=True,
    )



    created_at = models.DateTimeField(
        _("Review created at"),
        auto_now_add=True,
    )

    class Meta:
        verbose_name = _("Review")
        verbose_name_plural = _("Reviews")
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(order_item__isnull=False, order_box__isnull=True)
                    | models.Q(order_item__isnull=True, order_box__isnull=False)
                ),
                name="review_has_one_target",
            ),
        ]

    def __str__(self):
        target = self.order_item or self.order_box
        return f"{self.name or 'Anonymous'} - {target} - {self.rating}"




class Favorite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorites",
        verbose_name=_("Customer"),
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="favorited_by",
        verbose_name=_("Product"),
    )

    created_at = models.DateTimeField(_("Favorite created at"), auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"],
                name="unique_user_product_favorite",
            ),
        ]

        verbose_name = _("Favorite")
        verbose_name_plural = _("Favorites")

    def __str__(self):
        return f"{self.user_id} - {self.product_id}"
