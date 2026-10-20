
from django.urls import path

from .views import (
    FavoriteListAPIView,
    FavoriteDetailAPIView,
    BrandListAPIView,
    CategoryListAPIView,
    ProductListAPIView,
    ProductDetailAPIView,
    BoxListAPIView,
    AdminProductCreateAPIView,
    AdminProductVariantCreateAPIView,
    AdminProductImageCreateAPIView,
    AdminProductImageSetMainAPIView,
    AdminProductImageDeleteAPIView,
    AdminProductUpdateAPIView,
    AdminProductVariantUpdateAPIView,
    AdminProductPublishAPIView,
    AdminProductUnpublishAPIView,
    AdminBrandListCreateAPIView,
    AdminBrandDetailAPIView,
    BoxDetailAPIView,
    CollectionListAPIView,
    CollectionDetailAPIView,
    DailyOfferListAPIView,
    CartDetailAPIView,
    CartItemAddAPIView,
)


urlpatterns = [
    path("favorites/",FavoriteListAPIView.as_view(),name="favorite-list",),
    path("favorites/<int:product_id>/",FavoriteDetailAPIView.as_view(),name="favorite-detail",),
    path("brands/",BrandListAPIView.as_view(),name="brand-list",),
    path("categories/",CategoryListAPIView.as_view(),name="category-list",),
    path( "products/",ProductListAPIView.as_view(),name="product-list",),
    path("products/<int:product_id>/", ProductDetailAPIView.as_view(),name="product-detail",),
    path("boxes/",BoxListAPIView.as_view(),name="box-list",),
    path("boxes/<int:box_id>/",BoxDetailAPIView.as_view(),name="box-detail",),
    path("collections/",CollectionListAPIView.as_view(),name="collection-list",),
    path("collections/<slug:slug>/",CollectionDetailAPIView.as_view(),name="collection-detail",),
    path("offers/",DailyOfferListAPIView.as_view(),name="daily-offer-list",),
    path("cart/",CartDetailAPIView.as_view(),name="cart-detail",),
    path("cart/items/",CartItemAddAPIView.as_view(),name="cart-item-add",),

    path("admin/products/",AdminProductCreateAPIView.as_view(),name="admin-product-create",),
    path("admin/products/<int:product_id>/variants/",AdminProductVariantCreateAPIView.as_view(),name="admin-product-variant-create",),
    path("admin/products/<int:product_id>/images/",AdminProductImageCreateAPIView.as_view(),name="admin-product-image-create",),
    path("admin/products/<int:product_id>/images/<int:image_id>/main/",AdminProductImageSetMainAPIView.as_view(),name="admin-product-image-set-main",),
    path("admin/products/<int:product_id>/images/<int:image_id>/",AdminProductImageDeleteAPIView.as_view(),name="admin-product-image-delete",),
    path("admin/products/<int:product_id>/",AdminProductUpdateAPIView.as_view(),name="admin-product-update",),
    path("admin/variants/<int:variant_id>/",AdminProductVariantUpdateAPIView.as_view(),name="admin-product-variant-update",),

    path("admin/products/<int:product_id>/publish/",AdminProductPublishAPIView.as_view(),name="admin-product-publish",),
    path("admin/products/<int:product_id>/unpublish/",AdminProductUnpublishAPIView.as_view(),name="admin-product-unpublish",),

    path("admin/brands/",AdminBrandListCreateAPIView.as_view(),name="admin-brand-list",),
    path("admin/brands/<int:brand_id>/",AdminBrandDetailAPIView.as_view(),name="admin-brand-detail",),

]
