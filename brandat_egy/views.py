from django.utils import timezone
from decimal import Decimal
import re

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
from rest_framework.exceptions import ValidationError, NotFound

from collections import defaultdict


from .favorites import Favorites
from .catalog import get_catalog_queryset
from .pagination import ProductPagination
from .catalog_filters import apply_catalog_filters
from .catalog_search import apply_product_search
from .image_storage import delete_unused_product_image_file, delete_unused_box_image_file
from .box_catalog import get_box_catalog_queryset
from .cart import Cart
from .services import create_order_from_cart, cancel_order 
from .image_services import (
    create_image,
    set_main_image,
    delete_image,
)




from .serializers import (
    FavoriteProductSerializer,
    DailyOfferListSerializer,
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
    CartItemSerializer,
    CartAddItemSerializer,
    CartUpdateQuantitySerializer,
    CheckoutSerializer,
    CustomerOrderListSerializer,
    CustomerOrderDetailSerializer,
    ReviewListSerializer,
    ReviewCreateSerializer,
    BoxReviewCreateSerializer,
    AdminOrderListSerializer,
    AdminOrderQuerySerializer,
    AdminOrderDetailSerializer,
    AdminOrderStatusSerializer,
    AdminCategorySerializer,
    AdminCategoryQuerySerializer,
    AdminBoxWriteSerializer,
    AdminBoxListSerializer,
    AdminBoxDetailSerializer,
    AdminBoxQuerySerializer,
    AdminBoxItemCreateSerializer,
    AdminBoxItemUpdateSerializer,
    AdminBoxImageCreateSerializer,
    BoxItemSerializer,
    BoxImageSerializer,
    AdminCollectionWriteSerializer,
    AdminCollectionQuerySerializer,
    AdminCollectionListSerializer,
    AdminCollectionDetailSerializer,
    AdminCollectionBoxAddSerializer,
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
    Order,
    OrderItem,
    OrderBox,
    OrderBoxItem,
    Review,
    ShippingRate,

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
    pagination_class = ProductPagination

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
            .filter(boxes_count__gt=0)
            .order_by("name_ar", "pk")
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
            .filter(boxes_count__gt=0)
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
    

    def delete(self, request):
        cart = Cart(request)
        cart.clear()

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )
    

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
    


@method_decorator(csrf_protect, name="dispatch")
class CartItemDetailAPIView(APIView):
    permission_classes = [AllowAny]

    def get_cart_and_key(self, request, item_key):
        match = re.fullmatch(
            r"(variant|box):([1-9][0-9]*)",
            item_key,
        )

        if match is None:
            raise ValidationError({
                "key": "Invalid cart item key."
            })

        cart = Cart(request)

        if item_key not in cart.cart:
            from rest_framework.exceptions import NotFound
            raise NotFound("Item is not in the cart.")

        return cart, match.group(1), int(match.group(2))

    def patch(self, request, item_key):
        serializer = CartUpdateQuantitySerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        cart, item_type, item_id = (
            self.get_cart_and_key(request, item_key)
        )

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

        quantity = serializer.validated_data["quantity"]

        try:
            cart.update(item, quantity)
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )

        price = item.final_price

        cart_item = {
            "key": item_key,
            "type": item_type,
            "item": item,
            "quantity": quantity,
            "price": price,
            "total_price": price * quantity,
        }

        response_serializer = CartItemSerializer(
            cart_item,
            context={"request": request},
        )

        return Response({
            "item": response_serializer.data,
        })

    def delete(self, request, item_key):
        cart, item_type, item_id = (
            self.get_cart_and_key(request, item_key)
        )

        # Remove using the session key directly.
        # The item may have been deleted from the DB.
        del cart.cart[item_key]
        cart.save()

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )


class ShippingRateListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        rates = ShippingRate.objects.filter(is_active=True).order_by("name_ar")
        return Response([
            {
                "id": rate.pk,
                "name_ar": rate.name_ar,
                "fee": f"{rate.fee:.2f}",
            }
            for rate in rates
        ])


@method_decorator(csrf_protect, name="dispatch")
class CheckoutAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CheckoutSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        cart = Cart(request)

        user = (
            request.user
            if request.user.is_authenticated
            else None
        )

        try:
            order = create_order_from_cart(
                cart=cart,
                customer_name=data["customer_name"],
                phone=data["phone"],
                email=data["email"],
                address=data["address"],
                governorate=data["governorate"],
                user=user,
                session_key=request.session.session_key,
            )

        except ValueError as exc:
            message = str(exc)

            http_status = (
                status.HTTP_400_BAD_REQUEST
                if message == "Your cart is empty"
                else status.HTTP_409_CONFLICT
            )

            return Response(
                {"detail": message},
                status=http_status,
            )

        return Response(
            {
                "order_id": order.pk,
                "status": order.status,
                "total_price": (
                    f"{order.total_price:.2f}"
                ),
                "shipping_fee": f"{order.shipping_fee:.2f}",
                "governorate": (
                    order.governorate.name_ar if order.governorate_id else ""
                ),
                "created_at": order.created_at,
            },
            status=status.HTTP_201_CREATED,
        )
    

class CustomerOrderAccessMixin:
    def get_queryset(self):
        user = self.request.user

        if user.is_authenticated:
            queryset = Order.objects.filter(
                user=user,
            )
        else:
            session_key = self.request.session.session_key

            if not session_key:
                return Order.objects.none()

            queryset = Order.objects.filter(
                user__isnull=True,
                session_key=session_key,
            )

        order_items = (
            OrderItem.objects
            .select_related("variant__product")
            .order_by("pk")
        )

        order_box_items = (
            OrderBoxItem.objects
            .order_by("pk")
        )

        order_boxes = (
            OrderBox.objects
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=order_box_items,
                )
            )
            .order_by("pk")
        )

        return (
            queryset
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=order_items,
                ),
                Prefetch(
                    "boxes",
                    queryset=order_boxes,
                ),
            )
            .order_by("-created_at", "-pk")
        )


class CustomerOrderListAPIView(CustomerOrderAccessMixin,ListAPIView,):
    permission_classes = [AllowAny]

    serializer_class = CustomerOrderListSerializer
    pagination_class = ProductPagination


class CustomerOrderDetailAPIView(CustomerOrderAccessMixin,RetrieveAPIView,):
    permission_classes = [AllowAny]

    serializer_class = CustomerOrderDetailSerializer

    lookup_field = "pk"
    lookup_url_kwarg = "order_id"



class ReviewListAPIView(ListAPIView):
    permission_classes = [AllowAny]

    serializer_class = ReviewListSerializer
    pagination_class = ProductPagination

    def get_queryset(self):
        product = get_object_or_404(
            Product,
            pk=self.kwargs["product_id"],
            is_available=True,
        )

        return (
            Review.objects
            .filter(
                order_item__variant__product=product,
            )
            .order_by("-created_at", "-pk")
        )
    
    def post(self, request, product_id):
        product = get_object_or_404(
            Product,
            pk=product_id,
            is_available=True,
        )

        serializer = ReviewCreateSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        order_items = (
            OrderItem.objects
            .select_related("order", "variant")
        )

        if request.user.is_authenticated:
            order_items = order_items.filter(
                order__user=request.user,
            )
        else:
            session_key = request.session.session_key

            if not session_key:
                raise NotFound(
                    "Order item not found."
                )

            order_items = order_items.filter(
                order__user__isnull=True,
                order__session_key=session_key,
            )

        with transaction.atomic():
            order_item = get_object_or_404(
                order_items.select_for_update(
                    of=("self",)
                ),
                pk=data["order_item_id"],
                variant__product_id=product.pk,
            )

            if order_item.order.status != "delivered":
                raise ValidationError({
                    "order_item_id": (
                        "Only delivered orders "
                        "can be reviewed."
                    )
                })

            if Review.objects.filter(
                order_item=order_item
            ).exists():
                return Response(
                    {
                        "detail": (
                            "This order item has "
                            "already been reviewed."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            review = Review.objects.create(
                order_item=order_item,
                name=data["name"],
                rating=data["rating"],
                comment=data["comment"],
            )

        response_serializer = ReviewListSerializer(
            review
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
        )


class BoxReviewListAPIView(ListAPIView):
    permission_classes = [AllowAny]

    serializer_class = ReviewListSerializer
    pagination_class = ProductPagination

    def get_queryset(self):
        box = get_object_or_404(
            Box,
            pk=self.kwargs["box_id"],
            is_active=True,
        )

        return (
            Review.objects
            .filter(order_box__box=box)
            .order_by("-created_at", "-pk")
        )

    def post(self, request, box_id):
        box = get_object_or_404(
            Box,
            pk=box_id,
            is_active=True,
        )

        serializer = BoxReviewCreateSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        order_boxes = OrderBox.objects.select_related("order")

        if request.user.is_authenticated:
            order_boxes = order_boxes.filter(
                order__user=request.user,
            )
        else:
            session_key = request.session.session_key

            if not session_key:
                raise NotFound(
                    "Order box not found."
                )

            order_boxes = order_boxes.filter(
                order__user__isnull=True,
                order__session_key=session_key,
            )

        with transaction.atomic():
            order_box = get_object_or_404(
                order_boxes.select_for_update(
                    of=("self",)
                ),
                pk=data["order_box_id"],
                box_id=box.pk,
            )

            if order_box.order.status != "delivered":
                raise ValidationError({
                    "order_box_id": (
                        "Only delivered orders "
                        "can be reviewed."
                    )
                })

            if Review.objects.filter(
                order_box=order_box
            ).exists():
                return Response(
                    {
                        "detail": (
                            "This box has "
                            "already been reviewed."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            review = Review.objects.create(
                order_box=order_box,
                name=data["name"],
                rating=data["rating"],
                comment=data["comment"],
            )

        return Response(
            ReviewListSerializer(review).data,
            status=status.HTTP_201_CREATED,
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

    def perform_create(self, serializer):
        create_image(
            owner_model=Product,
            owner_id=self.kwargs["product_id"],
            image_model=ProductImage,
            owner_field="product",
            serializer=serializer,
        )


class AdminProductImageSetMainAPIView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, product_id, image_id):
        image = set_main_image(
            owner_model=Product,
            owner_id=product_id,
            image_model=ProductImage,
            owner_field="product",
            image_id=image_id,
        )

        serializer = AdminProductImageCreateSerializer(
            image,
            context={"request": request},
        )

        return Response(serializer.data)


class AdminProductImageDeleteAPIView(APIView):
    permission_classes = [IsAdminUser]

    def delete(self, request, product_id, image_id):
        delete_image(
            owner_model=Product,
            owner_id=product_id,
            image_model=ProductImage,
            owner_field="product",
            image_id=image_id,
            published_field="is_available",
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


class AdminOrderListAPIView(ListAPIView):
    serializer_class = AdminOrderListSerializer
    permission_classes = [IsAdminUser]
    pagination_class = ProductPagination

    def get_queryset(self):
        query_serializer = AdminOrderQuerySerializer(
            data=self.request.query_params.dict()
        )

        query_serializer.is_valid(
            raise_exception=True
        )

        filters = query_serializer.validated_data

        queryset = Order.objects.all()

        order_status = filters["status"]

        if order_status != "all":
            queryset = queryset.filter(
                status=order_status
            )

        search = filters.get("search", "")

        if search:
            search_filter = (
                Q(customer_name__icontains=search)
                | Q(phone__icontains=search)
            )

            if search.isdecimal() and len(search) <= 18:
                search_filter |= Q(pk=int(search))

            queryset = queryset.filter(search_filter)

        return (
            queryset
            .prefetch_related(
                "items",
                "boxes",
            )
            .order_by("-created_at", "-pk")
        )
    

def get_admin_order_detail_queryset():
    return (
        Order.objects
        .select_related("user")
        .prefetch_related(
            "items__variant__product",
            "boxes__items",
        )
    )

class AdminOrderDetailAPIView(RetrieveAPIView):
    permission_classes = [IsAdminUser]

    serializer_class = AdminOrderDetailSerializer

    lookup_field = "pk"
    lookup_url_kwarg = "order_id"

    def get_queryset(self):
        return get_admin_order_detail_queryset()



@method_decorator(csrf_protect, name="dispatch")
class AdminOrderStatusAPIView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, order_id):
        serializer = AdminOrderStatusSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data["status"]

        allowed_transitions = {
            "pending": "preparing",
            "confirmed": "preparing",
            "preparing": "shipped",
            "shipped": "delivered",
        }

        with transaction.atomic():
            order = get_object_or_404(
                Order.objects.select_for_update(),
                pk=order_id,
            )

            if order.status == new_status:
                changed = False

            elif allowed_transitions.get(order.status) != new_status:
                return Response(
                    {
                        "detail": (
                            f"Cannot change order status "
                            f"from {order.status} "
                            f"to {new_status}."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            else:
                order.status = new_status
                order.save(
                    update_fields=[
                        "status",
                        "updated_at",
                    ]
                )
                changed = True

        order = get_object_or_404(
            get_admin_order_detail_queryset(),
            pk=order_id,
        )

        return Response({
            "changed": changed,
            "order": AdminOrderDetailSerializer(
                order,
                context={"request": request},
            ).data,
        })
    

@method_decorator(csrf_protect, name="dispatch")
class AdminOrderCancelAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, order_id):
        if request.data:
            raise ValidationError({
                "detail": (
                    "Cancellation does not accept "
                    "a request body."
                )
            })

        try:
            cancel_order(order_id=order_id)

        except Order.DoesNotExist:
            raise NotFound("Order not found.")

        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )

        order = get_object_or_404(
            get_admin_order_detail_queryset(),
            pk=order_id,
        )

        return Response({
            "detail": "Order cancelled successfully.",
            "order": AdminOrderDetailSerializer(
                order,
                context={"request": request},
            ).data,
        })


@method_decorator(csrf_protect, name="dispatch")
class AdminCategoryListCreateAPIView(ListCreateAPIView):
    serializer_class = AdminCategorySerializer
    permission_classes = [IsAdminUser]
    pagination_class = ProductPagination

    def get_queryset(self):
        query_serializer = AdminCategoryQuerySerializer(
            data=self.request.query_params.dict()
        )

        query_serializer.is_valid(
            raise_exception=True
        )

        filters = query_serializer.validated_data

        queryset = Category.objects.select_related(
            "parent"
        )

        if "is_active" in filters:
            queryset = queryset.filter(
                is_active=filters["is_active"]
            )

        if "parent" in filters:
            queryset = queryset.filter(
                parent_id=filters["parent"]
            )

        search = filters.get("search", "")

        if search:
            queryset = queryset.filter(
                Q(name_ar__icontains=search)
                | Q(name_en__icontains=search)
                | Q(slug__icontains=search)
            )

        return queryset.order_by("name_en", "pk")


@method_decorator(csrf_protect, name="dispatch")
class AdminCategoryDetailAPIView(RetrieveUpdateAPIView):
    queryset = Category.objects.select_related("parent")

    serializer_class = AdminCategorySerializer
    permission_classes = [IsAdminUser]

    lookup_field = "pk"
    lookup_url_kwarg = "category_id"

    http_method_names = [
        "get",
        "patch",
        "head",
        "options",
    ]


@method_decorator(csrf_protect, name="dispatch")
class AdminBoxListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAdminUser]
    pagination_class = ProductPagination

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AdminBoxWriteSerializer

        return AdminBoxListSerializer

    def get_queryset(self):
        queryset = (
            Box.objects
            .annotate(
                items_count=Count(
                    "items",
                    distinct=True,
                )
            )
        )

        if self.request.method != "GET":
            return queryset

        query_serializer = AdminBoxQuerySerializer(
            data=self.request.query_params.dict()
        )
        query_serializer.is_valid(
            raise_exception=True
        )

        filters = query_serializer.validated_data

        if "is_active" in filters:
            queryset = queryset.filter(
                is_active=filters["is_active"]
            )

        search = filters.get("search", "")

        if search:
            queryset = queryset.filter(
                Q(name_ar__icontains=search)
                | Q(name_en__icontains=search)
                | Q(sku__icontains=search)
            )

        return queryset.order_by(
            "-created_at",
            "-pk",
        )

    def perform_create(self, serializer):
        serializer.save(
            is_active=False
        )


@method_decorator(csrf_protect, name="dispatch")
class AdminBoxDetailAPIView(RetrieveUpdateAPIView):
    permission_classes = [IsAdminUser]

    lookup_field = "pk"
    lookup_url_kwarg = "box_id"

    http_method_names = [
        "get",
        "patch",
        "head",
        "options",
    ]

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return AdminBoxWriteSerializer

        return AdminBoxDetailSerializer

    def get_queryset(self):
        return (
            Box.objects
            .annotate(
                items_count=Count(
                    "items",
                    distinct=True,
                )
            )
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=(
                        BoxItem.objects
                        .select_related("variant__product")
                        .order_by("pk")
                    ),
                ),
                Prefetch(
                    "images",
                    queryset=BoxImage.objects.order_by(
                        "-is_main",
                        "pk",
                    ),
                ),
            )
        )



def get_locked_draft_box(box_id):
    box = get_object_or_404(
        Box.objects.select_for_update(),
        pk=box_id,
    )

    if box.is_active:
        raise ValidationError({
            "box": (
                "Unpublish the box before "
                "changing its items."
            )
        })

    return box



@method_decorator(csrf_protect, name="dispatch")
class AdminBoxItemCreateAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, box_id):
        serializer = AdminBoxItemCreateSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        variant = serializer.validated_data["variant"]
        quantity = serializer.validated_data["quantity"]

        with transaction.atomic():
            box = get_locked_draft_box(box_id)

            if BoxItem.objects.filter(
                box=box,
                variant=variant,
            ).exists():
                return Response(
                    {
                        "detail": (
                            "This variant already exists "
                            "in the box."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            box_item = BoxItem.objects.create(
                box=box,
                variant=variant,
                quantity=quantity,
            )

        box_item = (
            BoxItem.objects
            .select_related("variant__product")
            .get(pk=box_item.pk)
        )

        return Response(
            BoxItemSerializer(box_item).data,
            status=status.HTTP_201_CREATED,
        )



@method_decorator(csrf_protect, name="dispatch")
class AdminBoxItemDetailAPIView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, box_id, item_id):
        serializer = AdminBoxItemUpdateSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        quantity = serializer.validated_data["quantity"]

        with transaction.atomic():
            box = get_locked_draft_box(box_id)

            box_item = get_object_or_404(
                BoxItem.objects.select_for_update(),
                pk=item_id,
                box=box,
            )

            box_item.quantity = quantity
            box_item.save(update_fields=["quantity"])

        box_item = (
            BoxItem.objects
            .select_related("variant__product")
            .get(pk=box_item.pk)
        )

        return Response(
            BoxItemSerializer(box_item).data
        )

    def delete(self, request, box_id, item_id):
        with transaction.atomic():
            box = get_locked_draft_box(box_id)

            box_item = get_object_or_404(
                BoxItem.objects.select_for_update(),
                pk=item_id,
                box=box,
            )

            box_item.delete()

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )



@method_decorator(csrf_protect, name="dispatch")
class AdminBoxImageCreateAPIView(APIView):
    permission_classes = [IsAdminUser]

    parser_classes = [
        MultiPartParser,
        FormParser,
    ]

    def post(self, request, box_id):
        serializer = AdminBoxImageCreateSerializer(
            data=request.data,
            context={"request": request},
        )

        serializer.is_valid(raise_exception=True)

        image = create_image(
            owner_model=Box,
            owner_id=box_id,
            image_model=BoxImage,
            owner_field="box",
            serializer=serializer,
        )

        return Response(
            BoxImageSerializer(
                image,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )


@method_decorator(csrf_protect, name="dispatch")
class AdminBoxImageSetMainAPIView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, box_id, image_id):
        image = set_main_image(
            owner_model=Box,
            owner_id=box_id,
            image_model=BoxImage,
            owner_field="box",
            image_id=image_id,
        )

        return Response(
            BoxImageSerializer(
                image,
                context={"request": request},
            ).data,
            status=status.HTTP_200_OK,
        )



@method_decorator(csrf_protect, name="dispatch")
class AdminBoxImageDeleteAPIView(APIView):
    permission_classes = [IsAdminUser]

    def delete(self, request, box_id, image_id):
        delete_image(
            owner_model=Box,
            owner_id=box_id,
            image_model=BoxImage,
            owner_field="box",
            image_id=image_id,
            published_field="is_active",
        )

        return Response(
            status=status.HTTP_204_NO_CONTENT,
        )
    

@method_decorator(csrf_protect, name="dispatch")
class AdminBoxPublishAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, box_id):
        with transaction.atomic():
            box = get_object_or_404(
                Box.objects.select_for_update(),
                pk=box_id,
            )

            if not box.is_active:
                errors = {}

                if (
                    not box.name_ar.strip()
                    or not box.description_ar.strip()
                ):
                    errors["box"] = (
                        "Arabic name and description "
                        "are required."
                    )

                if box.price <= 0:
                    errors["price"] = (
                        "Price must be greater than zero."
                    )

                if box.stock <= 0:
                    errors["stock"] = (
                        "Box must have available stock."
                    )

                has_main_image = (
                    BoxImage.objects.filter(
                        box=box,
                        is_main=True,
                    )
                    .exclude(image="")
                    .exists()
                )

                if not has_main_image:
                    errors["images"] = (
                        "Box must have a main image."
                    )

                items = list(
                    BoxItem.objects
                    .select_related("variant__product")
                    .filter(box=box)
                    .order_by("pk")
                )

                if not items:
                    errors["items"] = (
                        "Box must contain at least "
                        "one variant."
                    )

                invalid_items = []

                for item in items:
                    variant = item.variant

                    if (
                        not variant.is_active
                        or not variant.product.is_available
                        or variant.stock < item.quantity
                    ):
                        invalid_items.append(item.pk)

                if invalid_items:
                    errors["invalid_items"] = (
                        "These box item IDs have "
                        "inactive or insufficient-stock "
                        f"variants: {invalid_items}"
                    )

                if errors:
                    raise ValidationError(errors)

                box.is_active = True
                box.save(
                    update_fields=[
                        "is_active",
                        "updated_at",
                    ]
                )

        return Response({
            "id": box.pk,
            "is_active": box.is_active,
            "detail": "Box published successfully.",
        })



@method_decorator(csrf_protect, name="dispatch")
class AdminBoxUnpublishAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, box_id):
        with transaction.atomic():
            box = get_object_or_404(
                Box.objects.select_for_update(),
                pk=box_id,
            )

            if box.is_active:
                box.is_active = False
                box.save(
                    update_fields=[
                        "is_active",
                        "updated_at",
                    ]
                )

        return Response({
            "id": box.pk,
            "is_active": box.is_active,
            "detail": "Box unpublished successfully.",
        })



@method_decorator(csrf_protect, name="dispatch")
class AdminCollectionListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAdminUser]
    pagination_class = ProductPagination

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AdminCollectionWriteSerializer

        return AdminCollectionListSerializer

    def get_queryset(self):
        query_serializer = AdminCollectionQuerySerializer(
            data=self.request.query_params.dict()
        )
        query_serializer.is_valid(
            raise_exception=True
        )

        filters = query_serializer.validated_data

        queryset = Collection.objects.annotate(
            boxes_count=Count(
                "boxes",
                distinct=True,
            )
        )

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

    def perform_create(self, serializer):
        serializer.save(is_active=False)



@method_decorator(csrf_protect, name="dispatch")
class AdminCollectionDetailAPIView(RetrieveUpdateAPIView):
    permission_classes = [IsAdminUser]

    lookup_field = "pk"
    lookup_url_kwarg = "collection_id"

    http_method_names = [
        "get",
        "patch",
        "head",
        "options",
    ]

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return AdminCollectionWriteSerializer

        return AdminCollectionDetailSerializer

    def get_queryset(self):
        return (
            Collection.objects
            .annotate(
                boxes_count=Count(
                    "boxes",
                    distinct=True,
                )
            )
            .prefetch_related(
                Prefetch(
                    "boxes",
                    queryset=Box.objects.order_by(
                        "name_en",
                        "pk",
                    ),
                )
            )
        )



def get_locked_draft_collection(collection_id):
    collection = get_object_or_404(
        Collection.objects.select_for_update(),
        pk=collection_id,
    )

    if collection.is_active:
        raise ValidationError({
            "detail": (
                "Unpublish the collection before "
                "modifying its boxes."
            )
        })

    return collection



@method_decorator(csrf_protect, name="dispatch")
class AdminCollectionBoxAddAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, collection_id):
        serializer = AdminCollectionBoxAddSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        box = serializer.validated_data["box"]

        with transaction.atomic():
            collection = get_locked_draft_collection(
                collection_id
            )

            if collection.boxes.filter(
                pk=box.pk
            ).exists():
                return Response(
                    {
                        "detail": (
                            "This box already belongs "
                            "to the collection."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            collection.boxes.add(box)

        return Response(
            {
                "collection_id": collection.pk,
                "box_id": box.pk,
            },
            status=status.HTTP_201_CREATED,
        )



@method_decorator(csrf_protect, name="dispatch")
class AdminCollectionBoxRemoveAPIView(APIView):
    permission_classes = [IsAdminUser]

    def delete(self, request, collection_id, box_id):
        with transaction.atomic():
            collection = get_locked_draft_collection(
                collection_id
            )

            if not collection.boxes.filter(
                pk=box_id
            ).exists():
                raise NotFound(
                    "Box is not in this collection."
                )

            collection.boxes.remove(box_id)

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )


@method_decorator(csrf_protect, name="dispatch")
class AdminCollectionPublishAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, collection_id):
        with transaction.atomic():
            collection = get_object_or_404(
                Collection.objects.select_for_update(),
                pk=collection_id,
            )

            if collection.is_active:
                changed = False
            else:
                if not collection.boxes.filter(
                    is_active=True
                ).exists():
                    raise ValidationError({
                        "boxes": (
                            "The collection must contain "
                            "at least one published box."
                        )
                    })

                collection.is_active = True
                collection.save(
                    update_fields=["is_active"]
                )
                changed = True

        return Response({
            "id": collection.pk,
            "is_active": collection.is_active,
            "changed": changed,
        })


@method_decorator(csrf_protect, name="dispatch")
class AdminCollectionUnpublishAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, collection_id):
        with transaction.atomic():
            collection = get_object_or_404(
                Collection.objects.select_for_update(),
                pk=collection_id,
            )

            changed = collection.is_active

            if changed:
                collection.is_active = False
                collection.save(
                    update_fields=["is_active"]
                )

        return Response({
            "id": collection.pk,
            "is_active": collection.is_active,
            "changed": changed,
        })
