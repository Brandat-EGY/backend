from django.db import models
from decimal import Decimal
from django.conf import settings

from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError

from .pricing import get_effective_price
from .sku import generate_variant_sku

# Create your models here.

class Category(models.Model):
    name_ar = models.CharField(max_length=150)
    name_en = models.CharField(max_length=150)

    slug = models.SlugField(max_length=160, unique=True)

    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="children",
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name_ar


class Brand(models.Model):
    name_ar = models.CharField(max_length=150)
    name_en = models.CharField(max_length=150)

    slug = models.SlugField(max_length=160, unique=True)

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name_en

class Product(models.Model):
    name_ar = models.CharField(max_length=200)
    name_en = models.CharField(max_length=200, blank=True)

    description_ar = models.TextField()
    description_en = models.TextField(blank=True)

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        null=True,
        blank=True,
    )

    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name="products",
        null=True,
        blank=True,
    )

    scanned_code = models.CharField(
        max_length=512,
        null=True,
        blank=True,
    )


    is_available = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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

class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="variants",
    )

    sku = models.CharField(max_length=100, unique=True)

    size = models.CharField(max_length=100, blank=True)
    shade_ar = models.CharField(max_length=100, blank=True)
    shade_en = models.CharField(max_length=100, blank=True)

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    discount_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    sku = models.CharField(
        max_length=100,
        unique=True,
        default=generate_variant_sku,
        editable=False,
    )


    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
                "discount_price": (
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
    name_ar = models.CharField(max_length=200)
    name_en = models.CharField(max_length=200, blank=True)

    description_ar = models.TextField()
    description_en = models.TextField(blank=True)

    sku = models.CharField(max_length=100, unique=True)

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    discount_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name_ar
    
    
    def clean(self):
        super().clean()

        if (self.discount_price is not None and self.price is not None and self.discount_price >= self.price):
            raise ValidationError({
                "discount_price": ("Discount price must be lower than the price.")
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
    )

    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="box_items",
    )

    quantity = models.PositiveIntegerField(
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

    def __str__(self):
        return f"{self.box} - {self.variant} x {self.quantity}"

class BoxImage(models.Model):
    box = models.ForeignKey(
        Box,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="boxes/")
    is_main = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.box.name_ar


class Collection(models.Model):
    name_ar = models.CharField(max_length=200)
    name_en = models.CharField(max_length=200, blank=True)

    description_ar = models.TextField(blank=True)
    description_en = models.TextField(blank=True)

    slug = models.SlugField(max_length=200, unique=True)

    boxes = models.ManyToManyField(
        Box,
        related_name="collections",
        blank=True,
    )

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name_ar

class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images"
    )
    image = models.ImageField(
        upload_to="products/"
    )
    is_main = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_main=True),
                name="unique_main_image_per_product",
            ),
        ]


    def __str__(self):
        return f"Image for {self.product.name_ar}"

class Order(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="orders",
        null=True,
        blank=True,
    )


    session_key = models.CharField(
        max_length=40,
        null=True,
        blank=True,
    )

    customer_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    email = models.EmailField(
        blank=True,
    )

    address = models.TextField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    stock_restored_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    
    updated_at = models.DateTimeField(
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

        return products_total + boxes_total
    
    @property
    def is_guest(self):
        return self.user is None

    def __str__(self):
        return f"Order #{self.id} - {self.customer_name}"

class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )

    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="order_items",
    )

    quantity = models.PositiveIntegerField(
        default=1,
        validators=[
            MinValueValidator(1),
        ],
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

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
    )
    box = models.ForeignKey(
        Box,
        on_delete=models.PROTECT,
        related_name="order_boxes",
    )
    name_ar = models.CharField(max_length=200)
    name_en = models.CharField(max_length=200, blank=True)
    sku = models.CharField(max_length=100)

    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    @property
    def total_price(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.name_ar} x {self.quantity}"


class OrderBoxItem(models.Model):
    order_box = models.ForeignKey(
        OrderBox,
        on_delete=models.CASCADE,
        related_name="items",
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="order_box_items",
    )
    sku = models.CharField(max_length=100)
    product_name_ar = models.CharField(max_length=200)
    product_name_en = models.CharField(max_length=200, blank=True)

    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )

    def __str__(self):
        return f"{self.sku} x {self.quantity}"
    

class DailyOffer(models.Model):
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="daily_offers",
        null=True,
        blank=True,
    )
    box = models.ForeignKey(
        Box,
        on_delete=models.PROTECT,
        related_name="daily_offers",
        null=True,
        blank=True,
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        variant__isnull=False,
                        box__isnull=True,
                    )
                    | models.Q(
                        variant__isnull=True,
                        box__isnull=False,
                    )
                ),
                name="daily_offer_exactly_one_target",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    ends_at__gt=models.F("starts_at")
                ),
                name="daily_offer_end_after_start",
            ),
        ]

    def clean(self):
        super().clean()

        if (self.variant_id is None) == (self.box_id is None):
            raise ValidationError(
                "Choose either a variant or a box."
            )

        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.ends_at <= self.starts_at
        ):
            raise ValidationError({
                "ends_at": "End time must be after start time."
            })

        target = self.variant if self.variant_id else self.box

        if (
            target is not None
            and self.price is not None
            and self.price >= target.price
        ):
            raise ValidationError({
                "price": (
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
                overlapping_offers = overlapping_offers.exclude(
                    pk=self.pk,
                )

            if overlapping_offers.exists():
                raise ValidationError(
                    "An active offer already overlaps this period "
                    "for the same item."
                )

    def __str__(self):
        if self.variant_id:
            return f"Offer for {self.variant}"

        if self.box_id:
            return f"Offer for {self.box}"

        return "Daily offer"

class Review(models.Model):
    order_item = models.OneToOneField(
        OrderItem,
        on_delete=models.CASCADE,
        related_name="review",
    )
    name = models.CharField(
        max_length=100,
        blank=True,
    )

    rating = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(5),
        ]
    )

    comment = models.TextField(
        blank=True,
    )



    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    @property
    def product(self):
        return self.order_item.product

    def __str__(self):
        return f"{self.name or 'Anonymous'} - {self.product} - {self.rating}"




class Favorite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorites",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="favorited_by",
    )

    created_at = models.DateTimeField(auto_now_add=True,)

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"],
                name="unique_user_product_favorite",
            ),
        ]

    def __str__(self):
        return f"{self.user_id} - {self.product_id}"
