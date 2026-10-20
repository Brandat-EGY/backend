from .models import Favorite, Product
from django.db import transaction

class Favorites:
    SESSION_KEY = "favorite_products_v1"

    def __init__(self, request):
        self.request = request
        self.session = request.session

    def add(self, product):
        if product.pk is None:
            raise ValueError("Product must be saved first")

        if self.request.user.is_authenticated:
            _, created = Favorite.objects.get_or_create(
                user=self.request.user,
                product=product,
            )
            return created

        product_ids = self.session.get(self.SESSION_KEY, [])

        if product.pk in product_ids:
            return False

        self.session[self.SESSION_KEY] = [
            *product_ids,
            product.pk,
        ]
        return True

    def remove(self, product):
        if self.request.user.is_authenticated:
            deleted_count, _ = Favorite.objects.filter(
                user=self.request.user,
                product=product,
            ).delete()

            return deleted_count > 0

        product_ids = self.session.get(self.SESSION_KEY, [])

        if product.pk not in product_ids:
            return False

        self.session[self.SESSION_KEY] = [
            pk for pk in product_ids
            if pk != product.pk
        ]
        return True

    def contains(self, product):
        if self.request.user.is_authenticated:
            return Favorite.objects.filter(
                user=self.request.user,
                product=product,
            ).exists()

        product_ids = self.session.get(self.SESSION_KEY, [])
        return product.pk in product_ids

    def get_products(self):
        if self.request.user.is_authenticated:
            favorites = (
                Favorite.objects
                .filter(user=self.request.user)
                .select_related("product")
                .order_by("-created_at", "-pk")
            )

            return [
                favorite.product
                for favorite in favorites
            ]

        product_ids = self.session.get(self.SESSION_KEY, [])
        products = Product.objects.in_bulk(product_ids)

        return [
            products[pk]
            for pk in reversed(product_ids)
            if pk in products
        ]
    
    def merge_guest_favorites(self, *, user):
        if not user.is_authenticated:
            raise ValueError("User must be authenticated")

        product_ids = self.session.get(
            self.SESSION_KEY, []
        )

        if not product_ids:
            return

        existing_ids = Product.objects.filter(
            pk__in=product_ids,
        ).values_list("pk", flat=True)

        with transaction.atomic():
            Favorite.objects.bulk_create(
                [
                    Favorite(
                        user=user,
                        product_id=pk,
                    )
                    for pk in existing_ids
                ],
                ignore_conflicts=True,
            )

        self.session.pop(self.SESSION_KEY, None)
        self.session.modified = True