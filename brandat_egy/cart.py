from collections import defaultdict
from decimal import Decimal

from django.db.models import Prefetch

from .models import Box, BoxItem, ProductVariant


class Cart:
    SESSION_KEY = "cart_items_v2"

    def __init__(self, request):
        self.session = request.session

        cart = self.session.get(self.SESSION_KEY)

        if cart is None:
            cart = self.session[self.SESSION_KEY] = {}

        self.cart = cart

    def save(self):
        self.session.modified = True


    def _get_item_key(self, item):
        if isinstance(item, ProductVariant):
            return f"variant:{item.pk}"

        if isinstance(item, Box):
            return f"box:{item.pk}"

        raise ValueError("Unsupported cart item")

    def _get_available_stock(self, item):
        if isinstance(item, ProductVariant):
            if not item.can_purchase:
                return 0

            return item.stock

        if isinstance(item, Box):
            return item.available_stock

        raise ValueError("Unsupported cart item")
    
    def add(self, item, quantity=1):
        if type(quantity) is not int or quantity <= 0:
            raise ValueError("Quantity must be a positive integer")
        
        item_key = self._get_item_key(item)
        available_stock = self._get_available_stock(item)

        if available_stock <= 0:
            raise ValueError("This item is not available")

        current_quantity = self.cart.get(
            item_key, {}
        ).get("quantity", 0)

        new_quantity = current_quantity + quantity

        if new_quantity > available_stock:
            raise ValueError(
                "Requested quantity exceeds available stock"
            )

        self._ensure_combined_stock(item_key, new_quantity)

        self.cart[item_key] = {"quantity": new_quantity}
        self.save()





    def update(self, item, quantity):
        if type(quantity) is not int:
            raise ValueError("Quantity must be an integer")

        if quantity <= 0:
            self.remove(item)
            return
        
        item_key = self._get_item_key(item)
        available_stock = self._get_available_stock(item)

        if available_stock <= 0:
            raise ValueError("This item is not available")

        if quantity > available_stock:
            raise ValueError(
                "Requested quantity exceeds available stock"
            )

        self._ensure_combined_stock(item_key, quantity)

        self.cart[item_key] = {"quantity": quantity}
        self.save()


    def _ensure_combined_stock(self, item_key, quantity):
        proposed = {
            key: saved["quantity"]
            for key, saved in self.cart.items()
        }
        proposed[item_key] = quantity

        variant_ids = []
        box_ids = []

        for key in proposed:
            kind, raw_id = key.split(":", 1)

            if kind == "variant":
                variant_ids.append(int(raw_id))
            elif kind == "box":
                box_ids.append(int(raw_id))
            else:
                raise ValueError("Unsupported cart item")

        boxes = {
            box.pk: box
            for box in Box.objects.filter(pk__in=box_ids).prefetch_related(
                Prefetch(
                    "items",
                    queryset=BoxItem.objects.select_related(
                        "variant__product"
                    ),
                )
            )
        }

        variant_need = defaultdict(int)

        for key, line_quantity in proposed.items():
            kind, raw_id = key.split(":", 1)
            item_id = int(raw_id)

            if kind == "variant":
                variant_need[item_id] += line_quantity
                continue

            box = boxes.get(item_id)

            if box is None:
                raise ValueError("An item in your cart no longer exists")

            if not box.is_active or line_quantity > box.stock:
                raise ValueError(
                    "Requested quantity exceeds available stock"
                )

            box_items = list(box.items.all())

            if not box_items:
                raise ValueError(
                    "Requested quantity exceeds available stock"
                )

            for box_item in box_items:
                variant_need[box_item.variant_id] += (
                    box_item.quantity * line_quantity
                )

        variants = {
            variant.pk: variant
            for variant in ProductVariant.objects.select_related(
                "product"
            ).filter(pk__in=variant_need)
        }

        for variant_id, needed in variant_need.items():
            variant = variants.get(variant_id)

            if variant is None:
                raise ValueError("An item in your cart no longer exists")

            if (
                not variant.is_active
                or not variant.product.is_available
                or needed > variant.stock
            ):
                raise ValueError(
                    "Requested quantity exceeds available stock"
                )

    def remove(self, item):
        item_key = self._get_item_key(item)

        if item_key in self.cart:
            del self.cart[item_key]
            self.save()

    def clear(self):
        self.cart = {}
        self.session[self.SESSION_KEY] = self.cart
        self.save()

    def __len__(self):
        return sum(
            item["quantity"]
            for item in self.cart.values()
        )

    def __iter__(self):
        variant_ids = []
        box_ids = []

        for item_key in self.cart:
            item_type, item_id = item_key.split(":", 1)

            if item_type == "variant":
                variant_ids.append(item_id)
            elif item_type == "box":
                box_ids.append(item_id)
            else:
                raise ValueError("Unsupported cart item")

        variants = ProductVariant.objects.select_related(
            "product"
        ).filter(pk__in=variant_ids)

        boxes = Box.objects.filter(pk__in=box_ids)

        objects_by_key = {
            f"variant:{variant.pk}": variant
            for variant in variants
        }

        objects_by_key.update({
            f"box:{box.pk}": box
            for box in boxes
        })

        for item_key, saved_item in self.cart.items():
            item = objects_by_key.get(item_key)

            if item is None:
                raise ValueError(
                    "An item in your cart no longer exists"
                )

            item_type = item_key.split(":", 1)[0]
            quantity = saved_item["quantity"]
            price = item.final_price

            yield {
                "key": item_key,
                "type": item_type,
                "item": item,
                "quantity": quantity,
                "price": price,
                "total_price": price * quantity,
            }
    
    def get_total_price(self):
        return sum(
            (item["total_price"] for item in self),
            Decimal("0.00"),
        )