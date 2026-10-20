from django.contrib import admin
from .models import (
    Category,
    Brand,
    Order,
    OrderItem,
    Product,
    ProductImage,
    Review,
    ProductVariant,
    Box, 
    BoxItem, 
    BoxImage,
    OrderBox,
    OrderBoxItem,
    Collection,
    DailyOffer,
    Favorite
)
from django.contrib import messages
from .services import cancel_order

# Register your models here.

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1

class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name_ar",
        "name_en",
        "category",
        "brand",
        "is_available",
        "created_at",
    )

    list_filter = ("is_available","category", "brand")
    search_fields = ("name_ar","name_en","description_ar","description_en",)    
    inlines = (ProductImageInline, ProductVariantInline)

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ("variant", "quantity", "price")

    def has_add_permission(self, request, obj=None):
        return False

class OrderBoxInline(admin.TabularInline):
    model = OrderBox
    extra = 0
    can_delete = False
    show_change_link = True

    fields = (
        "name_ar",
        "sku",
        "quantity",
        "price",
        "total_price",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "customer_name", "phone", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("customer_name", "phone", "email")
    readonly_fields = ("status", "stock_restored_at", "created_at", "updated_at", "total_price",)
    inlines = (OrderItemInline, OrderBoxInline)

    actions = ("cancel_selected_orders",)

    @admin.action(description="Cancel selected pending orders")
    def cancel_selected_orders(self, request, queryset):
        cancelled_count = 0

        for order in queryset.order_by("pk"):
            try:
                result = cancel_order(order_id=order.pk)
            except ValueError as error:
                self.message_user(
                    request,
                    f"Order #{order.pk}: {error}",
                    level=messages.WARNING,
                )
            else:
                if order.stock_restored_at is None:
                    cancelled_count += 1

        if cancelled_count:
            self.message_user(
                request,
                f"{cancelled_count} orders cancelled and stock restored.",
                level=messages.SUCCESS,
            )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("order_item", "rating", "name", "created_at")
    list_filter = ("rating",)
    search_fields = ("name", "comment")

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name_ar", "name_en", "parent", "is_active")
    list_filter = ("is_active", "parent")
    search_fields = ("name_ar", "name_en")
    prepopulated_fields = {"slug": ("name_en",)}


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name_ar", "name_en", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name_ar", "name_en")
    prepopulated_fields = {"slug": ("name_en",)}



class BoxItemInline(admin.TabularInline):
    model = BoxItem
    extra = 1


class BoxImageInline(admin.TabularInline):
    model = BoxImage
    extra = 1



@admin.register(Box)
class BoxAdmin(admin.ModelAdmin):
    list_display = (
        "name_ar",
        "name_en",
        "sku",
        "price",
        "discount_price",
        "stock",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("name_ar", "name_en", "sku")
    readonly_fields = ("created_at", "updated_at")
    inlines = (BoxItemInline, BoxImageInline)


class OrderBoxItemInline(admin.TabularInline):
    model = OrderBoxItem
    extra = 0
    can_delete = False

    fields = (
        "variant",
        "sku",
        "product_name_ar",
        "product_name_en",
        "quantity",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(OrderBox)
class OrderBoxAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "name_ar",
        "quantity",
        "price",
        "total_price",
    )
    search_fields = (
        "name_ar",
        "name_en",
        "sku",
        "order__customer_name",
        "order__phone",
    )
    readonly_fields = (
        "order",
        "box",
        "name_ar",
        "name_en",
        "sku",
        "quantity",
        "price",
        "total_price",
    )
    inlines = (OrderBoxItemInline,)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
    

@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("name_ar", "name_en", "slug", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name_ar", "name_en", "slug")

    prepopulated_fields = {"slug": ("name_en",)}
    filter_horizontal = ("boxes",)


@admin.register(DailyOffer)
class DailyOfferAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "variant",
        "box",
        "price",
        "starts_at",
        "ends_at",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = (
        "variant__sku",
        "variant__product__name_ar",
        "variant__product__name_en",
        "box__sku",
        "box__name_ar",
        "box__name_en",
    )


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "product",
        "created_at",
    )

    search_fields = (
        "user__phone",
        "user__customer_name",
        "product__name_ar",
        "product__name_en",
    )

    list_filter = ("created_at",)

    readonly_fields = ("created_at",)
