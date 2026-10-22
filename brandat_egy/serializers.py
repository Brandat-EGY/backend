from django.db.models import Avg, Count


from rest_framework import serializers

from decimal import Decimal

from .box_catalog import (
    get_box_catalog_price,
    get_box_catalog_stock,
)


from .models import (
    Product, 
    Category, 
    Brand, 
    ProductImage, 
    ProductVariant, 
    Review,
    Box,
    BoxImage,
    BoxItem,
    Collection,
    DailyOffer,
    Order,
    OrderItem,
    OrderBox,
    OrderBoxItem,
)

class FavoriteProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ('id', 'name_ar','name_en', 'is_available')

        read_only_fields = fields


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = (
            "id",
            "name_ar",
            "name_en",
            "slug",
        )


class CategorySerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = (
            "id",
            "name_ar",
            "name_en",
            "slug",
            "children",
        )

    def get_children(self, obj):
        children_map = self.context["children_map"]

        children = children_map.get(obj.pk, [])

        return CategorySerializer(
            children,
            many=True,
            context=self.context,
        ).data
    

class CatalogCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = (
            "id",
            "name_ar",
            "name_en",
            "slug",
        )


class ProductListSerializer(serializers.ModelSerializer):
    brand = BrandSerializer(read_only=True)

    category = CatalogCategorySerializer(
        read_only=True
    )

    starting_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        allow_null=True,
        read_only=True,
    )

    in_stock = serializers.BooleanField(
        read_only=True
    )

    main_image = serializers.SerializerMethodField()
    is_favorite = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name_ar",
            "name_en",
            "brand",
            "category",
            "main_image",
            "starting_price",
            "in_stock",
            "is_favorite",
        )

    def get_main_image(self, obj):
        images = getattr(obj, "catalog_images", [])

        if not images:
            return None

        image = images[0].image

        if not image:
            return None

        request = self.context.get("request")

        if request is None:
            return image.url

        return request.build_absolute_uri(image.url)

    def get_is_favorite(self, obj):
        request = self.context["request"]

        if request.user.is_authenticated:
            return bool(obj.catalog_is_favorite)

        guest_ids = self.context.get(
            "guest_favorite_ids",
            set(),
        )

        return obj.pk in guest_ids
    


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = (
            "id",
            "image",
            "is_main",
        )

class AdminProductImageCreateSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(
        required=True,
        allow_empty_file=False,
    )

    class Meta:
        model = ProductImage

        fields = (
            "id",
            "image",
            "is_main",
            "created_at",
        )

        read_only_fields = (
            "id",
            "created_at",
        )

    def validate_image(self, image):
        max_size = 5 * 1024 * 1024

        if image.size > max_size:
            raise serializers.ValidationError(
                "Image size must not exceed 5 MB."
            )

        allowed_formats = {
            "JPEG",
            "PNG",
            "WEBP",
        }

        image_format = getattr(
            getattr(image, "image", None),
            "format",
            None,
        )

        if image_format not in allowed_formats:
            raise serializers.ValidationError(
                "Only JPEG, PNG and WebP "
                "images are allowed."
            )

        return image

    def validate(self, attrs):
        allowed_fields = {
            "image",
            "is_main",
        }

        unexpected_fields = (
            set(self.initial_data.keys())
            - allowed_fields
        )

        if unexpected_fields:
            raise serializers.ValidationError({
                field: "This field is not allowed."
                for field in sorted(unexpected_fields)
            })

        return attrs


class ProductVariantSerializer(serializers.ModelSerializer):
    final_price = serializers.SerializerMethodField()
    can_purchase = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = (
            "id",
            "sku",
            "size",
            "shade_ar",
            "shade_en",
            "price",
            "discount_price",
            "final_price",
            "stock",
            "can_purchase",
        )

    def get_final_price(self, obj):
        base_price = (
            obj.discount_price
            if obj.discount_price is not None
            else obj.price
        )

        active_offers = obj.catalog_active_offers

        if active_offers:
            base_price = min(
                base_price,
                active_offers[0].price,
            )

        return f"{base_price:.2f}"

    def get_can_purchase(self, obj):
        return obj.is_active and obj.stock > 0


class ProductDetailSerializer(ProductListSerializer):
    images = ProductImageSerializer(
        source="catalog_images",
        many=True,
        read_only=True,
    )

    variants = ProductVariantSerializer(
        source="catalog_variants",
        many=True,
        read_only=True,
    )

    average_rating = serializers.SerializerMethodField()
    reviews_count = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + (
            "description_ar",
            "description_en",
            "images",
            "variants",
            "average_rating",
            "reviews_count",
        )

    def _get_review_stats(self, obj):
        if not hasattr(obj, "_catalog_review_stats"):
            obj._catalog_review_stats = (
                Review.objects.filter(
                    order_item__variant__product_id=obj.pk
                ).aggregate(
                    average=Avg("rating"),
                    count=Count("pk"),
                )
            )

        return obj._catalog_review_stats

    def get_average_rating(self, obj):
        stats = self._get_review_stats(obj)

        return round(
            float(stats["average"] or 0),
            2,
        )

    def get_reviews_count(self, obj):
        stats = self._get_review_stats(obj)

        return stats["count"]

    
class ProductCatalogQuerySerializer(serializers.Serializer):
    search = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=120,
        trim_whitespace=True,
    )

    brand = serializers.CharField(
        required=False,
        max_length=1000,
    )

    category = serializers.CharField(
        required=False,
        max_length=160,
    )

    min_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
    )

    max_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
    )

    available_only = serializers.BooleanField(
        required=False,
        default=False,
    )

    ordering = serializers.ChoiceField(
        choices=(
            "relevance",
            "newest",
            "price_asc",
            "price_desc",
            "brand_az",
            "category_az",
        ),
        required=False,
    )


    def validate_brand(self, value):
        slugs = [
            slug.strip().lower()
            for slug in value.split(",")
        ]

        if not all(slugs):
            raise serializers.ValidationError(
                "Brand slugs cannot be empty."
            )

        if len(slugs) > 20:
            raise serializers.ValidationError(
                "Maximum 20 brands allowed."
            )

        return list(dict.fromkeys(slugs))

    def validate_category(self, value):
        return value.strip().lower()

    def validate(self, attrs):
        min_price = attrs.get("min_price")
        max_price = attrs.get("max_price")

        if (
            min_price is not None
            and max_price is not None
            and min_price > max_price
        ):
            raise serializers.ValidationError({
                "min_price": (
                    "Minimum price cannot exceed "
                    "maximum price."
                )
            })
        
        search = attrs.get("search", "")

        if len(search.split()) > 6:
            raise serializers.ValidationError({
                "search": "Maximum 6 search words allowed."
            })

        if "ordering" not in attrs:
            attrs["ordering"] = (
                "relevance" if search else "newest"
            )

        if attrs["ordering"] == "relevance" and not search:
            raise serializers.ValidationError({
                "ordering": (
                    "Relevance ordering requires a search query."
                )
            })


        return attrs


class BoxListSerializer(serializers.ModelSerializer):
    final_price = serializers.SerializerMethodField()
    available_stock = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()
    main_image = serializers.SerializerMethodField()

    class Meta:
        model = Box

        fields = (
            "id",
            "name_ar",
            "name_en",
            "sku",
            "price",
            "discount_price",
            "final_price",
            "available_stock",
            "in_stock",
            "main_image",
        )

        read_only_fields = fields

    def get_final_price(self, obj):
        price = get_box_catalog_price(obj)

        return f"{price:.2f}"

    def _get_available_stock(self, obj):
        if not hasattr(obj, "_catalog_available_stock"):
            obj._catalog_available_stock = (
                get_box_catalog_stock(obj)
            )

        return obj._catalog_available_stock

    def get_available_stock(self, obj):
        return self._get_available_stock(obj)

    def get_in_stock(self, obj):
        return self._get_available_stock(obj) > 0

    def get_main_image(self, obj):
        images = obj.catalog_images

        if not images:
            return None

        image = images[0].image

        if not image:
            return None

        request = self.context.get("request")

        if request is None:
            return image.url

        return request.build_absolute_uri(image.url)



class BoxImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = BoxImage

        fields = (
            "id",
            "image",
            "is_main",
        )

        read_only_fields = fields


class BoxItemProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product

        fields = (
            "id",
            "name_ar",
            "name_en",
            "is_available",
        )

        read_only_fields = fields


class BoxItemVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant

        fields = (
            "id",
            "sku",
            "size",
            "shade_ar",
            "shade_en",
        )

        read_only_fields = fields


class BoxItemSerializer(serializers.ModelSerializer):
    product = BoxItemProductSerializer(
        source="variant.product",
        read_only=True,
    )

    variant = BoxItemVariantSerializer(
        read_only=True,
    )

    class Meta:
        model = BoxItem

        fields = (
            "id",
            "quantity",
            "product",
            "variant",
        )

        read_only_fields = fields


class BoxDetailSerializer(BoxListSerializer):
    images = BoxImageSerializer(
        source="catalog_images",
        many=True,
        read_only=True,
    )

    items = BoxItemSerializer(
        source="catalog_items",
        many=True,
        read_only=True,
    )

    class Meta(BoxListSerializer.Meta):
        fields = BoxListSerializer.Meta.fields + (
            "description_ar",
            "description_en",
            "images",
            "items",
        )

        read_only_fields = fields



class CollectionListSerializer(serializers.ModelSerializer):
    boxes_count = serializers.IntegerField(
        read_only=True,
    )

    class Meta:
        model = Collection

        fields = (
            "id",
            "name_ar",
            "name_en",
            "slug",
            "description_ar",
            "description_en",
            "boxes_count",
        )

        read_only_fields = fields



class CollectionDetailSerializer(CollectionListSerializer):
    boxes = BoxListSerializer(
        source="catalog_boxes",
        many=True,
        read_only=True,
    )

    class Meta(CollectionListSerializer.Meta):
        fields = CollectionListSerializer.Meta.fields + (
            "boxes",
        )

        read_only_fields = fields


class DailyOfferListSerializer(serializers.ModelSerializer):
    target_type = serializers.SerializerMethodField()
    target = serializers.SerializerMethodField()
    price_before_offer = serializers.SerializerMethodField()

    offer_price = serializers.DecimalField(
        source="price",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )

    final_price = serializers.SerializerMethodField()
    available_stock = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()

    class Meta:
        model = DailyOffer

        fields = (
            "id",
            "target_type",
            "target",
            "price_before_offer",
            "offer_price",
            "final_price",
            "available_stock",
            "in_stock",
            "starts_at",
            "ends_at",
        )

        read_only_fields = fields

    def get_target_type(self, obj):
        if obj.variant_id is not None:
            return "product_variant"

        return "box"

    def _image_url(self, images):
        if not images:
            return None

        image = images[0].image

        if not image:
            return None

        request = self.context.get("request")

        if request is None:
            return image.url

        return request.build_absolute_uri(image.url)

    def get_target(self, obj):
        if obj.variant_id is not None:
            variant = obj.variant
            product = variant.product

            return {
                "product_id": product.pk,
                "variant_id": variant.pk,
                "name_ar": product.name_ar,
                "name_en": product.name_en,
                "sku": variant.sku,
                "size": variant.size,
                "shade_ar": variant.shade_ar,
                "shade_en": variant.shade_en,
                "main_image": self._image_url(
                    product.catalog_images
                ),
            }

        box = obj.box

        return {
            "box_id": box.pk,
            "name_ar": box.name_ar,
            "name_en": box.name_en,
            "sku": box.sku,
            "main_image": self._image_url(
                box.catalog_images
            ),
        }

    def _base_price(self, obj):
        item = (
            obj.variant
            if obj.variant_id is not None
            else obj.box
        )

        if item.discount_price is not None:
            return item.discount_price

        return item.price

    def get_price_before_offer(self, obj):
        return f"{self._base_price(obj):.2f}"

    def get_final_price(self, obj):
        final_price = min(
            self._base_price(obj),
            obj.price,
        )

        return f"{final_price:.2f}"

    def get_available_stock(self, obj):
        if not hasattr(obj, "_catalog_available_stock"):
            if obj.variant_id is not None:
                variant = obj.variant

                stock = (
                    variant.stock
                    if variant.can_purchase
                    else 0
                )
            else:
                stock = get_box_catalog_stock(
                    obj.box
                )

            obj._catalog_available_stock = stock

        return obj._catalog_available_stock

    def get_in_stock(self, obj):
        return self.get_available_stock(obj) > 0


class CartItemSerializer(serializers.Serializer):
    key = serializers.CharField()
    type = serializers.CharField()
    quantity = serializers.IntegerField()

    price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    total_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    details = serializers.SerializerMethodField()

    def _get_image_url(self, image_obj):
        if image_obj is None or not image_obj.image:
            return None

        image_url = image_obj.image.url
        request = self.context.get("request")

        if request is None:
            return image_url

        return request.build_absolute_uri(image_url)

    def get_details(self, obj):
        item = obj["item"]

        if isinstance(item, ProductVariant):
            product = item.product

            return {
                "id": item.pk,
                "product_id": product.pk,
                "name_ar": product.name_ar,
                "name_en": product.name_en,
                "sku": item.sku,
                "size": item.size,
                "shade_ar": item.shade_ar,
                "shade_en": item.shade_en,
                "available_stock": (
                    item.stock if item.can_purchase else 0
                ),
                "can_purchase": item.can_purchase,
                "main_image": self._get_image_url(
                    product.main_image
                ),
            }

        if isinstance(item, Box):
            stock = item.available_stock

            return {
                "id": item.pk,
                "name_ar": item.name_ar,
                "name_en": item.name_en,
                "sku": item.sku,
                "available_stock": stock,
                "can_purchase": stock > 0,
                "main_image": self._get_image_url(
                    item.main_image
                ),
            }

        return None


class CartAddItemSerializer(serializers.Serializer):
    type = serializers.ChoiceField(
        choices=("variant", "box"),
    )

    item_id = serializers.IntegerField(
        min_value=1,
    )

    quantity = serializers.IntegerField(
        min_value=1,
        default=1,
    )

    def validate(self, attrs):
        allowed_fields = {
            "type",
            "item_id",
            "quantity",
        }

        unexpected_fields = (
            set(self.initial_data) - allowed_fields
        )

        if unexpected_fields:
            raise serializers.ValidationError({
                field: "This field is not allowed."
                for field in sorted(unexpected_fields)
            })

        return attrs
    

class CartUpdateQuantitySerializer(serializers.Serializer):
    quantity = serializers.IntegerField(
        min_value=1,
    )

    def validate(self, attrs):
        allowed_fields = {"quantity"}

        unexpected_fields = (
            set(self.initial_data) - allowed_fields
        )

        if unexpected_fields:
            raise serializers.ValidationError({
                field: "This field is not allowed."
                for field in sorted(unexpected_fields)
            })

        return attrs
    

class CheckoutSerializer(serializers.Serializer):
    customer_name = serializers.CharField(
        max_length=150,
    )

    phone = serializers.CharField(
        max_length=20,
    )

    email = serializers.EmailField(
        required=False,
        allow_blank=True,
        default="",
    )

    address = serializers.CharField(
        max_length=1000,
    )

    def validate(self, attrs):
        allowed_fields = {
            "customer_name",
            "phone",
            "email",
            "address",
        }

        unexpected = (
            set(self.initial_data) - allowed_fields
        )

        if unexpected:
            raise serializers.ValidationError({
                field: "This field is not allowed."
                for field in sorted(unexpected)
            })

        return attrs
    

class CustomerOrderItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(
        source="variant.product_id",
        read_only=True,
    )

    product_name_ar = serializers.CharField(
        source="variant.product.name_ar",
        read_only=True,
    )

    product_name_en = serializers.CharField(
        source="variant.product.name_en",
        read_only=True,
    )

    sku = serializers.CharField(
        source="variant.sku",
        read_only=True,
    )

    size = serializers.CharField(
        source="variant.size",
        read_only=True,
    )

    unit_price = serializers.DecimalField(
        source="price",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )

    total_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = OrderItem
        fields = (
            "id",
            "product_id",
            "product_name_ar",
            "product_name_en",
            "variant",
            "sku",
            "size",
            "quantity",
            "unit_price",
            "total_price",
        )
        read_only_fields = fields


class CustomerOrderBoxItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderBoxItem
        fields = (
            "id",
            "variant",
            "sku",
            "product_name_ar",
            "product_name_en",
            "quantity",
        )
        read_only_fields = fields


class CustomerOrderBoxSerializer(serializers.ModelSerializer):
    items = CustomerOrderBoxItemSerializer(
        many=True,
        read_only=True,
    )

    total_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = OrderBox
        fields = (
            "id",
            "box",
            "name_ar",
            "name_en",
            "sku",
            "quantity",
            "price",
            "total_price",
            "items",
        )
        read_only_fields = fields


class CustomerOrderListSerializer(serializers.ModelSerializer):
    total_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    payment_method = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "status",
            "payment_method",
            "total_price",
            "created_at",
        )
        read_only_fields = fields

    def get_payment_method(self, obj):
        return "cash_on_delivery"


class CustomerOrderDetailSerializer(CustomerOrderListSerializer):
    items = CustomerOrderItemSerializer(
        many=True,
        read_only=True,
    )

    boxes = CustomerOrderBoxSerializer(
        many=True,
        read_only=True,
    )

    class Meta(CustomerOrderListSerializer.Meta):
        fields = CustomerOrderListSerializer.Meta.fields + (
            "customer_name",
            "phone",
            "email",
            "address",
            "updated_at",
            "items",
            "boxes",
        )
        read_only_fields = fields

class ReviewListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review

        fields = (
            "id",
            "name",
            "rating",
            "comment",
            "created_at",
        )

        read_only_fields = fields


class ReviewCreateSerializer(serializers.Serializer):
    order_item_id = serializers.IntegerField(
        min_value=1,
    )

    name = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        default="",
    )

    rating = serializers.IntegerField(
        min_value=1,
        max_value=5,
    )

    comment = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )

    def validate(self, attrs):
        allowed_fields = {
            "order_item_id",
            "name",
            "rating",
            "comment",
        }

        unexpected = (
            set(self.initial_data) - allowed_fields
        )

        if unexpected:
            raise serializers.ValidationError({
                field: "This field is not allowed."
                for field in sorted(unexpected)
            })

        return attrs

class AdminProductCreateSerializer(serializers.ModelSerializer):
    brand = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )

    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Product
        fields = (
            "id",
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "brand",
            "scanned_code",
            "category",
            "is_available",
            "created_at",
        )

        read_only_fields = (
            "id",
            "is_available",
            "created_at",
        )

    def validate_scanned_code(self, value):
        if value is None:
            return None

        return value.strip() or None


    def validate(self, attrs):
        allowed_fields = {
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "scanned_code",
            "brand",
            "category",
        }

        unexpected_fields = (
            set(self.initial_data) - allowed_fields
        )

        if unexpected_fields:
            raise serializers.ValidationError({
                field: (
                    "This field cannot be provided "
                    "during product creation."
                )
                for field in sorted(unexpected_fields)
            })

        return attrs
    


class AdminProductVariantCreateSerializer(
    serializers.ModelSerializer
):
    class Meta:
        model = ProductVariant

        fields = (
            "id",
            "product",
            "sku",
            "size",
            "shade_ar",
            "shade_en",
            "price",
            "discount_price",
            "stock",
            "is_active",
            "created_at",
        )

        read_only_fields = (
            "id",
            "sku",
            "product",
            "is_active",
            "created_at",
        )

    def validate(self, attrs):
        allowed_fields = {
            "size",
            "shade_ar",
            "shade_en",
            "price",
            "discount_price",
            "stock",
        }

        unexpected_fields = (
            set(self.initial_data) - allowed_fields
        )

        if unexpected_fields:
            raise serializers.ValidationError({
                field: (
                    "This field cannot be provided "
                    "during variant creation."
                )
                for field in sorted(unexpected_fields)
            })

        price = attrs.get("price")
        discount_price = attrs.get("discount_price")

        if (
            discount_price is not None
            and price is not None
            and discount_price >= price
        ):
            raise serializers.ValidationError({
                "discount_price": (
                    "Discount price must be lower "
                    "than the regular price."
                )
            })

        return attrs
    


class AdminProductUpdateSerializer(serializers.ModelSerializer):
    brand = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )

    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Product

        fields = (
            "id",
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "scanned_code",
            "brand",
            "category",
            "is_available",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "is_available",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        allowed_fields = {
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "scanned_code",
            "brand",
            "category",
        }
        
  
    def validate_scanned_code(self, value):
        if value is None:
            return None

        return value.strip() or None


    def validate(self, attrs):
        allowed_fields = {
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "scanned_code",
            "brand",
            "category",
        }

        unexpected_fields = (
            set(self.initial_data) - allowed_fields
        )

        if unexpected_fields:
            raise serializers.ValidationError({
                field: "This field cannot be updated here."
                for field in sorted(unexpected_fields)
            })

        return attrs

    

class AdminProductVariantUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant

        fields = (
            "id",
            "product",
            "sku",
            "size",
            "shade_ar",
            "shade_en",
            "price",
            "discount_price",
            "stock",
            "is_active",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "product",
            "sku",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        allowed_fields = {
            "size",
            "shade_ar",
            "shade_en",
            "price",
            "discount_price",
            "stock",
            "is_active",
        }

        unexpected_fields = (
            set(self.initial_data) - allowed_fields
        )

        if unexpected_fields:
            raise serializers.ValidationError({
                field: "This field cannot be updated."
                for field in sorted(unexpected_fields)
            })

        price = attrs.get(
            "price",
            self.instance.price,
        )

        discount_price = attrs.get(
            "discount_price",
            self.instance.discount_price,
        )

        if (
            discount_price is not None
            and discount_price >= price
        ):
            raise serializers.ValidationError({
                "discount_price": (
                    "Discount price must be lower "
                    "than the regular price."
                )
            })

        return attrs
    

class AdminProductListSerializer(serializers.ModelSerializer):
    brand = BrandSerializer(read_only=True)

    category = CatalogCategorySerializer(
        read_only=True
    )

    main_image = serializers.SerializerMethodField()

    starting_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
        allow_null=True,
    )

    in_stock = serializers.BooleanField(
        read_only=True
    )

    variants_count = serializers.IntegerField(
        read_only=True
    )

    class Meta:
        model = Product

        fields = (
            "id",
            "name_ar",
            "name_en",
            "scanned_code",
            "brand",
            "category",
            "main_image",
            "starting_price",
            "in_stock",
            "variants_count",
            "is_available",
            "created_at",
            "updated_at",
        )

    def get_main_image(self, obj):
        images = obj.catalog_images

        if not images:
            return None

        image = images[0].image

        if not image:
            return None

        request = self.context.get("request")

        if request is None:
            return image.url

        return request.build_absolute_uri(image.url)
    

class AdminProductListQuerySerializer(serializers.Serializer):
    search = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=120,
        trim_whitespace=True,
    )

    status = serializers.ChoiceField(
        choices=(
            "all",
            "draft",
            "published",
        ),
        required=False,
        default="all",
    )

    brand = serializers.IntegerField(
        required=False,
        min_value=1,
    )

    category = serializers.IntegerField(
        required=False,
        min_value=1,
    )

    scanned_code = serializers.CharField(
        required=False,
        max_length=512,
        trim_whitespace=True,
    )

    def validate_search(self, value):
        if len(value.split()) > 6:
            raise serializers.ValidationError(
                "Maximum 6 search words allowed."
            )

        return value
    

class AdminProductDetailVariantSerializer(ProductVariantSerializer):
    class Meta(ProductVariantSerializer.Meta):
        fields = ProductVariantSerializer.Meta.fields + (
            "is_active",
            "created_at",
            "updated_at",
        )

    def get_can_purchase(self, obj):
        return obj.can_purchase


class AdminProductDetailSerializer(AdminProductListSerializer):
    images = ProductImageSerializer(
        source="catalog_images",
        many=True,
        read_only=True,
    )

    variants = AdminProductDetailVariantSerializer(
        source="catalog_variants",
        many=True,
        read_only=True,
    )

    class Meta(AdminProductListSerializer.Meta):
        fields = AdminProductListSerializer.Meta.fields + (
            "description_ar",
            "description_en",
            "images",
            "variants",
        )



class AdminBrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand

        fields = (
            "id",
            "name_ar",
            "name_en",
            "slug",
            "is_active",
        )

        read_only_fields = ("id",)

    def validate_slug(self, value):
        slug = value.strip().lower()

        queryset = Brand.objects.filter(
            slug__iexact=slug
        )

        if self.instance is not None:
            queryset = queryset.exclude(
                pk=self.instance.pk
            )

        if queryset.exists():
            raise serializers.ValidationError(
                "A brand with this slug already exists."
            )

        return slug

    def validate(self, attrs):
        allowed_fields = {
            "name_ar",
            "name_en",
            "slug",
            "is_active",
        }

        unexpected = (
            set(self.initial_data) - allowed_fields
        )

        if unexpected:
            raise serializers.ValidationError({
                field: "This field is not allowed."
                for field in sorted(unexpected)
            })

        return attrs


class AdminBrandQuerySerializer(serializers.Serializer):
    search = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=120,
    )

    is_active = serializers.BooleanField(
        required=False,
    )



class AdminOrderListSerializer(CustomerOrderListSerializer):
    is_guest = serializers.BooleanField(
        read_only=True,
    )

    class Meta(CustomerOrderListSerializer.Meta):
        fields = CustomerOrderListSerializer.Meta.fields + (
            "customer_name",
            "phone",
            "address",
            "is_guest",
        )

        read_only_fields = fields


class AdminOrderQuerySerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=(
            "all",
            "pending",
            "paid",
            "shipped",
            "delivered",
            "cancelled",
        ),
        required=False,
        default="all",
    )

    search = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=100,
        trim_whitespace=True,
    )


class AdminOrderDetailSerializer(CustomerOrderDetailSerializer):
    user_id = serializers.IntegerField(
        read_only=True,
    )

    is_guest = serializers.BooleanField(
        read_only=True,
    )

    stock_restored_at = serializers.DateTimeField(
        read_only=True,
    )

    class Meta(CustomerOrderDetailSerializer.Meta):
        fields = CustomerOrderDetailSerializer.Meta.fields + (
            "user_id",
            "is_guest",
            "stock_restored_at",
        )

        read_only_fields = fields


class AdminOrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=("shipped", "delivered"),
    )

    def validate(self, attrs):
        allowed_fields = {"status"}

        unexpected = set(self.initial_data) - allowed_fields

        if unexpected:
            raise serializers.ValidationError({
                field: "This field is not allowed."
                for field in sorted(unexpected)
            })

        return attrs
