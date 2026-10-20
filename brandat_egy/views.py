from django.utils import timezone
from decimal import Decimal

from django.db.models import Exists, OuterRef, Prefetch, Count, Q
from django.db import transaction

from django.shortcuts import render, get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect


from rest_framework.generics import (
    ListAPIView, 
    RetrieveAPIView, 
    CreateAPIView, 
    UpdateAPIView, 
    ListCreateAPIView, 
    RetrieveUpdateAPIView
)

from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework import status
from rest_framework.exceptions import ValidationError

from collections import defaultdict


from .favorites import Favorites
from .catalog import get_catalog_queryset
from .pagination import ProductPagination
from .catalog_filters import apply_catalog_filters
from .catalog_search import apply_product_search
from .image_storage import delete_unused_product_image_file
from .box_catalog import get_box_catalog_queryset
from .cart import Cart




from .serializers import (
    FavoriteProductSerializer, 
    BrandSerializer, 
    CategorySerializer, 
    ProductListSerializer, 
    ProductCatalogQuerySerializer, 
    ProductDetailSerializer, 
    AdminProductCreateSerializer, 
    AdminProductVariantCreateSerializer,
    AdminProductImageCreateSerializer,
    AdminProductUpdateSerializer,
    AdminProductVariantUpdateSerializer,
    AdminProductListSerializer,
    AdminProductListQuerySerializer,
    AdminProductDetailSerializer,
    AdminBrandSerializer,
    AdminBrandQuerySerializer,
    BoxListSerializer,
    BoxDetailSerializer,
    CollectionListSerializer,
    CollectionDetailSerializer,
    DailyOfferListSerializer,
    CartItemSerializer,
    CartAddItemSerializer,
)
from .models import (
    Product, 
    Category, 
    Brand, 
    Favorite, 
    ProductImage, 
    DailyOffer, 
    ProductVariant,
    Box,
    Collection,
    BoxImage,
    BoxItem,

)


# Create your views here.

class FavoriteListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        favorites = Favorites(request)

        products = favorites.get_products()

        serializer = FavoriteProductSerializer(
            products,
            many=True,
        )

        return Response({
            "count": len(products),
            "results": serializer.data,
        })



@method_decorator(csrf_protect, name="dispatch")
class FavoriteDetailAPIView(APIView):
    permission_classes = [AllowAny]

    def get_product(self, product_id):
        return get_object_or_404(
            Product,
            pk=product_id,
        )

    def get(self, request, product_id):
        product = self.get_product(product_id)

        favorites = Favorites(request)

        return Response({
            "product_id": product.id,
            "is_favorite": favorites.contains(product),
        })

    def post(self, request, product_id):
        product = self.get_product(product_id)

        favorites = Favorites(request)
        created = favorites.add(product)

        return Response(
            {
                "product_id": product.id,
                "is_favorite": True,
                "created": created,
            },
            status=(
                status.HTTP_201_CREATED
                if created
                else status.HTTP_200_OK
            ),
        )

    def delete(self, request, product_id):
        product = self.get_product(product_id)

        favorites = Favorites(request)
        removed = favorites.remove(product)

        return Response({
            "product_id": product.id,
            "is_favorite": False,
            "removed": removed,
        })


class BrandListAPIView(ListAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    serializer_class = BrandSerializer
    pagination_class = None

    def get_queryset(self):
        return Brand.objects.filter(
            is_active=True
        ).order_by("name_en", "pk")



class CategoryListAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        categories = Category.objects.filter(
            is_active=True
        ).order_by("name_en", "pk")

        children_map = defaultdict(list)

        for category in categories:
            children_map[category.parent_id].append(
                category
            )

        root_categories = children_map.get(None, [])

        serializer = CategorySerializer(
            root_categories,
            many=True,
            context={
                "children_map": children_map,
            },
        )

        return Response(serializer.data)


class ProductListAPIView(ListAPIView):
    permission_classes = [AllowAny]

    serializer_class = ProductListSerializer
    pagination_class = ProductPagination

    def get_queryset(self):
        query_serializer = ProductCatalogQuerySerializer(
            data=self.request.query_params
        )

        query_serializer.is_valid(
            raise_exception=True
        )

        filters = query_serializer.validated_data

        queryset = get_catalog_queryset(
            available_only=filters["available_only"]
        )

        queryset = apply_product_search(
            queryset,
            filters.get("search", ""),
        )
        
        queryset = apply_catalog_filters(
            queryset,
            filters,
        )

        if self.request.user.is_authenticated:
            queryset = queryset.annotate(
                catalog_is_favorite=Exists(
                    Favorite.objects.filter(
                        user_id=self.request.user.pk,
                        product_id=OuterRef("pk"),
                    )
                )
            )

        return queryset.prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.order_by(
                    "-is_main",
                    "pk",
                ),
                to_attr="catalog_images",
            )
        )


    
    def get_serializer_context(self):
        context = super().get_serializer_context()

        if not self.request.user.is_authenticated:
            context["guest_favorite_ids"] = set(
                self.request.session.get(
                    Favorites.SESSION_KEY,
                    [],
                )
            )

        return context



class ProductDetailAPIView(RetrieveAPIView):
    permission_classes = [AllowAny]

    serializer_class = ProductDetailSerializer

    lookup_field = "pk"
    lookup_url_kwarg = "product_id"

    def get_queryset(self):
        at = timezone.now()

        active_offers = (
            DailyOffer.objects.filter(
                is_active=True,
                starts_at__lte=at,
                ends_at__gt=at,
            )
            .order_by("price", "pk")
        )

        variants = (
            ProductVariant.objects.filter(
                is_active=True
            )
            .order_by("pk")
            .prefetch_related(
                Prefetch(
                    "daily_offers",
                    queryset=active_offers,
                    to_attr="catalog_active_offers",
                )
            )
        )

        queryset = (
            get_catalog_queryset(at=at)
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.order_by(
                        "-is_main",
                        "pk",
                    ),
                    to_attr="catalog_images",
                ),
                Prefetch(
                    "variants",
                    queryset=variants,
                    to_attr="catalog_variants",
                ),
            )
        )

        if self.request.user.is_authenticated:
            queryset = queryset.annotate(
                catalog_is_favorite=Exists(
                    Favorite.objects.filter(
                        user_id=self.request.user.pk,
                        product_id=OuterRef("pk"),
                    )
                )
            )

        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()

        if not self.request.user.is_authenticated:
            context["guest_favorite_ids"] = set(
                self.request.session.get(
                    Favorites.SESSION_KEY,
                    [],
                )
            )

        return context
    

class BoxListAPIView(ListAPIView):
    permission_classes = [AllowAny]

    serializer_class = BoxListSerializer
    pagination_class = ProductPagination

    def get_queryset(self):
        return get_box_catalog_queryset()
    


class BoxDetailAPIView(RetrieveAPIView):
    permission_classes = [AllowAny]

    serializer_class = BoxDetailSerializer

    lookup_field = "pk"
    lookup_url_kwarg = "box_id"

    def get_queryset(self):
        return get_box_catalog_queryset()
    


class CollectionListAPIView(ListAPIView):
    permission_classes = [AllowAny]

    serializer_class = CollectionListSerializer
    pagination_class = ProductPagination

    def get_queryset(self):
        return (
            Collection.objects
            .filter(is_active=True)
            .annotate(
                boxes_count=Count(
                    "boxes",
                    filter=Q(boxes__is_active=True),
                    distinct=True,
                )
            )
            .order_by("name_en", "pk")
        )
    


class CollectionDetailAPIView(RetrieveAPIView):
    permission_classes = [AllowAny]

    serializer_class = CollectionDetailSerializer

    lookup_field = "slug"
    lookup_url_kwarg = "slug"

    def get_queryset(self):
        return (
            Collection.objects
            .filter(is_active=True)
            .annotate(
                boxes_count=Count(
                    "boxes",
                    filter=Q(boxes__is_active=True),
                    distinct=True,
                )
            )
            .prefetch_related(
                Prefetch(
                    "boxes",
                    queryset=get_box_catalog_queryset(),
                    to_attr="catalog_boxes",
                )
            )
        )
    

class DailyOfferListAPIView(ListAPIView):
    permission_classes = [AllowAny]

    serializer_class = DailyOfferListSerializer
    pagination_class = ProductPagination

    def get_queryset(self):
        now = timezone.now()

        return (
            DailyOffer.objects
            .filter(
                is_active=True,
                starts_at__lte=now,
                ends_at__gt=now,
            )
            .filter(
                Q(
                    variant__is_active=True,
                    variant__product__is_available=True,
                )
                |
                Q(box__is_active=True)
            )
            .select_related(
                "variant__product",
                "box",
            )
            .prefetch_related(
                Prefetch(
                    "variant__product__images",
                    queryset=ProductImage.objects.order_by(
                        "-is_main",
                        "pk",
                    ),
                    to_attr="catalog_images",
                ),
                Prefetch(
                    "box__images",
                    queryset=BoxImage.objects.order_by(
                        "-is_main",
                        "pk",
                    ),
                    to_attr="catalog_images",
                ),
                Prefetch(
                    "box__items",
                    queryset=BoxItem.objects.select_related(
                        "variant__product"
                    ),
                    to_attr="catalog_items",
                ),
            )
            .order_by("ends_at", "pk")
        )


class CartDetailAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        cart = Cart(request)

        try:
            items = list(cart)
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = CartItemSerializer(
            items,
            many=True,
            context={"request": request},
        )

        total_price = sum(
            (item["total_price"] for item in items),
            Decimal("0.00"),
        )

        total_quantity = sum(
            item["quantity"]
            for item in items
        )

        return Response({
            "count": len(items),
            "total_quantity": total_quantity,
            "total_price": f"{total_price:.2f}",
            "items": serializer.data,
        })
    

@method_decorator(csrf_protect, name="dispatch")
class CartItemAddAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CartAddItemSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        item_type = data["type"]
        item_id = data["item_id"]
        quantity = data["quantity"]

        if item_type == "variant":
            item = get_object_or_404(
                ProductVariant.objects.select_related(
                    "product"
                ),
                pk=item_id,
            )
        else:
            item = get_object_or_404(
                Box,
                pk=item_id,
            )

        cart = Cart(request)

        item_key = f"{item_type}:{item.pk}"
        created = item_key not in cart.cart

        try:
            cart.add(item, quantity=quantity)

        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )

        new_quantity = cart.cart[item_key]["quantity"]

        price = item.final_price

        cart_item = {
            "key": item_key,
            "type": item_type,
            "item": item,
            "quantity": new_quantity,
            "price": price,
            "total_price": price * new_quantity,
        }

        response_serializer = CartItemSerializer(
            cart_item,
            context={"request": request},
        )

        return Response(
            {
                "created": created,
                "item": response_serializer.data,
            },
            status=(
                status.HTTP_201_CREATED
                if created
                else status.HTTP_200_OK
            ),
        )


# -----------------ADMIN-----------------------

class AdminProductCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAdminUser]

    serializer_class = AdminProductCreateSerializer
    pagination_class = ProductPagination

    def get_serializer_class(self):
        if self.request.method == "GET":
            return AdminProductListSerializer

        return AdminProductCreateSerializer

    def get_queryset(self):
        query_serializer = AdminProductListQuerySerializer(
            data=self.request.query_params
        )
        query_serializer.is_valid(
            raise_exception=True
        )

        filters = query_serializer.validated_data

        queryset = get_catalog_queryset(
            include_unavailable=True
        )

        queryset = queryset.select_related(
            "brand",
            "category",
        )

        if filters["status"] == "draft":
            queryset = queryset.filter(
                is_available=False
            )

        elif filters["status"] == "published":
            queryset = queryset.filter(
                is_available=True
            )

        if filters.get("brand") is not None:
            queryset = queryset.filter(
                brand_id=filters["brand"]
            )

        if filters.get("category") is not None:
            queryset = queryset.filter(
                category_id=filters["category"]
            )

        if filters.get("scanned_code"):
            queryset = queryset.filter(
                scanned_code=filters["scanned_code"]
            )

        search = filters.get("search", "")

        if search:
            queryset = apply_product_search(
                queryset,
                search,
            )

            queryset = queryset.order_by(
                "-search_score",
                "-created_at",
                "-pk",
            )
        else:
            queryset = queryset.order_by(
                "-created_at",
                "-pk",
            )

        queryset = queryset.annotate(
            variants_count=Count(
                "variants",
                distinct=True,
            )
        )

        return queryset.prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.order_by(
                    "-is_main",
                    "pk",
                ),
                to_attr="catalog_images",
            )
        )

    def perform_create(self, serializer):
        serializer.save(
            is_available=False
        )

class AdminProductVariantCreateAPIView(CreateAPIView):
    serializer_class = AdminProductVariantCreateSerializer
    permission_classes = [IsAdminUser]

    def get_serializer_context(self):
        context = super().get_serializer_context()

        context["parent_product"] = get_object_or_404(
            Product,
            pk=self.kwargs["product_id"],
        )

        return context

    def perform_create(self, serializer):
        product = serializer.context["parent_product"]

        serializer.save(
            product=product,
        )



class AdminProductImageCreateAPIView(CreateAPIView):
    queryset = ProductImage.objects.all()

    serializer_class = AdminProductImageCreateSerializer
    permission_classes = [IsAdminUser]

    parser_classes = [
        MultiPartParser,
        FormParser,
    ]

    @transaction.atomic
    def perform_create(self, serializer):
        product = get_object_or_404(
            Product.objects.select_for_update(),
            pk=self.kwargs["product_id"],
        )

        make_main = serializer.validated_data.get(
            "is_main",
            False,
        )

        has_images = ProductImage.objects.filter(
            product=product
        ).exists()

        if not has_images:
            make_main = True

        if make_main:
            ProductImage.objects.filter(
                product=product,
                is_main=True,
            ).update(
                is_main=False
            )

        serializer.save(
            product=product,
            is_main=make_main,
        )



class AdminProductImageSetMainAPIView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, product_id, image_id):
        with transaction.atomic():
            product = get_object_or_404(
                Product.objects.select_for_update(),
                pk=product_id,
            )

            image = get_object_or_404(
                ProductImage,
                pk=image_id,
                product=product,
            )

            ProductImage.objects.filter(
                product=product,
                is_main=True,
            ).exclude(
                pk=image.pk,
            ).update(
                is_main=False,
            )

            if not image.is_main:
                image.is_main = True
                image.save(
                    update_fields=["is_main"]
                )

        serializer = AdminProductImageCreateSerializer(
            image,
            context={"request": request},
        )

        return Response(serializer.data)
    

class AdminProductImageDeleteAPIView(APIView):
    permission_classes = [IsAdminUser]

    def delete(self, request, product_id, image_id):
        with transaction.atomic():
            product = get_object_or_404(
                Product.objects.select_for_update(),
                pk=product_id,
            )

            image = get_object_or_404(
                ProductImage,
                pk=image_id,
                product=product,
            )

            remaining_images = (
                ProductImage.objects.filter(
                    product=product,
                )
                .exclude(pk=image.pk)
            )

            # Published products must retain an image.
            if (
                product.is_available
                and not remaining_images.exists()
            ):
                raise ValidationError({
                    "image": (
                        "Cannot delete the last image "
                        "of a published product."
                    )
                })

            filename = image.image.name
            storage = image.image.storage

            # Delete the database record first.
            image.delete()

            remaining_images = ProductImage.objects.filter(
                product=product
            )

            # Preserve an existing main image if possible.
            main_image = (
                remaining_images.filter(
                    is_main=True,
                )
                .order_by("pk")
                .first()
            )

            # Otherwise choose the first remaining image.
            if main_image is None:
                main_image = (
                    remaining_images.order_by("pk").first()
                )

            if main_image is not None:
                remaining_images.filter(
                    is_main=True,
                ).exclude(
                    pk=main_image.pk,
                ).update(
                    is_main=False,
                )

                if not main_image.is_main:
                    remaining_images.filter(
                        pk=main_image.pk,
                    ).update(
                        is_main=True,
                    )

            # Delete the physical file after DB commit.
            transaction.on_commit(
                lambda filename=filename, storage=storage:
                    delete_unused_product_image_file(
                        filename=filename,
                        storage=storage,
                    )
            )

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )



class AdminProductUpdateAPIView(RetrieveUpdateAPIView):
    permission_classes = [IsAdminUser]

    lookup_field = "pk"
    lookup_url_kwarg = "product_id"

    http_method_names = [
        "get",
        "patch",
        "head",
        "options",
    ]

    def get_serializer_class(self):
        if self.request.method == "GET":
            return AdminProductDetailSerializer

        return AdminProductUpdateSerializer

    def get_queryset(self):
        if self.request.method != "GET":
            return Product.objects.all()

        at = timezone.now()

        active_offers = (
            DailyOffer.objects.filter(
                is_active=True,
                starts_at__lte=at,
                ends_at__gt=at,
            )
            .order_by("price", "pk")
        )

        variants = (
            ProductVariant.objects
            .select_related("product")
            .order_by("pk")
            .prefetch_related(
                Prefetch(
                    "daily_offers",
                    queryset=active_offers,
                    to_attr="catalog_active_offers",
                )
            )
        )

        return (
            get_catalog_queryset(
                at=at,
                include_unavailable=True,
            )
            .annotate(
                variants_count=Count(
                    "variants",
                    distinct=True,
                )
            )
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.order_by(
                        "-is_main",
                        "pk",
                    ),
                    to_attr="catalog_images",
                ),
                Prefetch(
                    "variants",
                    queryset=variants,
                    to_attr="catalog_variants",
                ),
            )
        )



class AdminProductVariantUpdateAPIView(UpdateAPIView):
    serializer_class = AdminProductVariantUpdateSerializer
    permission_classes = [IsAdminUser]

    lookup_field = "pk"
    lookup_url_kwarg = "variant_id"

    http_method_names = [
        "patch",
        "options",
    ]

    def get_queryset(self):
        if self.request.method == "PATCH":
            return ProductVariant.objects.select_for_update()

        return ProductVariant.objects.all()

    @transaction.atomic
    def patch(self, request, *args, **kwargs):
        variant = get_object_or_404(
            ProductVariant.objects.only("product_id"),
            pk=self.kwargs["variant_id"],
        )

        get_object_or_404(
            Product.objects.select_for_update(),
            pk=variant.product_id,
        )

        return super().patch(request, *args, **kwargs)
    

class AdminProductPublishAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, product_id):
        with transaction.atomic():
            product = get_object_or_404(
                Product.objects.select_for_update(),
                pk=product_id,
            )

            if not product.is_available:
                errors = {}

                # Check the required product details.
                if (
                    not product.name_ar.strip()
                    or not product.description_ar.strip()
                ):
                    errors["product"] = (
                        "Product name and description "
                        "are required."
                    )

                # At least one sellable variant.
                has_valid_variant = (
                    ProductVariant.objects.filter(
                        product=product,
                        is_active=True,
                        stock__gt=0,
                        price__gt=0,
                    ).exists()
                )

                if not has_valid_variant:
                    errors["variants"] = (
                        "Product must have at least one "
                        "active variant with available stock."
                    )

                # A main image must be assigned.
                has_main_image = (
                    ProductImage.objects.filter(
                        product=product,
                        is_main=True,
                    )
                    .exclude(image="")
                    .exists()
                )

                if not has_main_image:
                    errors["images"] = (
                        "Product must have a main image."
                    )

                if errors:
                    raise ValidationError(errors)

                product.is_available = True
                product.save(
                    update_fields=[
                        "is_available",
                        "updated_at",
                    ]
                )

        serializer = AdminProductUpdateSerializer(
            product,
            context={"request": request},
        )

        return Response(serializer.data)
    


class AdminProductUnpublishAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, product_id):
        with transaction.atomic():
            product = get_object_or_404(
                Product.objects.select_for_update(),
                pk=product_id,
            )

            if product.is_available:
                product.is_available = False
                product.save(
                    update_fields=[
                        "is_available",
                        "updated_at",
                    ]
                )

        serializer = AdminProductUpdateSerializer(
            product,
            context={"request": request},
        )

        return Response(serializer.data)
    


class AdminBrandListCreateAPIView(ListCreateAPIView):
    serializer_class = AdminBrandSerializer
    permission_classes = [IsAdminUser]
    pagination_class = ProductPagination

    def get_queryset(self):
        query_serializer = AdminBrandQuerySerializer(
            data=self.request.query_params.dict()
        )

        query_serializer.is_valid(
            raise_exception=True
        )

        filters = query_serializer.validated_data

        queryset = Brand.objects.all()

        if "is_active" in filters:
            queryset = queryset.filter(
                is_active=filters["is_active"]
            )

        search = filters.get("search", "")

        if search:
            queryset = queryset.filter(
                Q(name_ar__icontains=search)
                | Q(name_en__icontains=search)
                | Q(slug__icontains=search)
            )

        return queryset.order_by("name_en", "pk")


class AdminBrandDetailAPIView(RetrieveUpdateAPIView):
    queryset = Brand.objects.all()
    serializer_class = AdminBrandSerializer
    permission_classes = [IsAdminUser]

    lookup_field = "pk"
    lookup_url_kwarg = "brand_id"

    http_method_names = [
        "get",
        "patch",
        "head",
        "options",
    ]
