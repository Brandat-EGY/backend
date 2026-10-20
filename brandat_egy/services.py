from collections import defaultdict

from django.db import transaction
from .pricing import get_effective_price


from .models import (
    Box,
    BoxItem,
    Order,
    OrderBox,
    OrderBoxItem,
    OrderItem,
    Product,
    ProductVariant,
)
from django.utils import timezone


@transaction.atomic
def create_order_from_cart(*, cart, customer_name, phone, address, user=None, session_key=None, email="",):
    items = list(cart)

    if not items:
        raise ValueError("Your cart is empty")

    variant_quantities = defaultdict(int)
    box_quantities = defaultdict(int)

    for item in items:
        quantity = item["quantity"]

        if type(quantity) is not int or quantity <= 0:
            raise ValueError("Quantity must be a positive integer")

        if item["type"] == "variant":
            variant_quantities[item["item"].pk] += quantity
        elif item["type"] == "box":
            box_quantities[item["item"].pk] += quantity
        else:
            raise ValueError("Unsupported cart item")

    boxes = {
        box.pk: box
        for box in Box.objects.select_for_update()
        .filter(pk__in=box_quantities)
        .order_by("pk")
    }

    for box_id, quantity in box_quantities.items():
        box = boxes.get(box_id)

        if box is None:
            raise ValueError("A box no longer exists")

        if not box.is_active:
            raise ValueError(f"Box {box.name_ar} is not available")

        if quantity > box.stock:
            raise ValueError(
                f"Only {box.stock} boxes available for {box.name_ar}"
            )

    box_items_by_box = defaultdict(list)

    box_items = (
        BoxItem.objects.select_for_update()
        .filter(box_id__in=box_quantities)
        .order_by("pk")
    )

    for box_item in box_items:
        if box_item.quantity <= 0:
            raise ValueError("Invalid box item quantity")

        box_items_by_box[box_item.box_id].append(box_item)

        variant_quantities[box_item.variant_id] += (
            box_item.quantity * box_quantities[box_item.box_id]
        )

    for box_id in box_quantities:
        if not box_items_by_box[box_id]:
            raise ValueError(
                f"Box {boxes[box_id].name_ar} has no items"
            )

    product_ids = set(
        ProductVariant.objects.filter(
            pk__in=variant_quantities
        ).values_list("product_id", flat=True)
    )

    products = {
        product.pk: product
        for product in Product.objects.select_for_update()
        .filter(pk__in=product_ids)
        .order_by("pk")
    }

    variants = {
        variant.pk: variant
        for variant in ProductVariant.objects.select_for_update()
        .filter(pk__in=variant_quantities)
        .order_by("pk")
    }

    for variant_id, quantity in variant_quantities.items():
        variant = variants.get(variant_id)

        if variant is None:
            raise ValueError("A variant no longer exists")

        product = products.get(variant.product_id)

        if (
            product is None
            or not product.is_available
            or not variant.is_active
        ):
            raise ValueError(
                f"Variant {variant.sku} is no longer available"
            )

        if quantity > variant.stock:
            raise ValueError(
                f"Only {variant.stock} items available for "
                f"{product.name_ar} - {variant.sku}; "
                f"your cart requires {quantity}"
            )
    
    pricing_at = timezone.now()

    order = Order.objects.create(
        user=user,
        session_key=session_key,
        customer_name=customer_name,
        phone=phone,
        email=email,
        address=address,
    )

    for item in items:
        quantity = item["quantity"]

        if item["type"] == "variant":
            variant = variants[item["item"].pk]

            OrderItem.objects.create(
                order=order,
                variant=variant,
                quantity=quantity,
                price=get_effective_price(variant, at=pricing_at,),
            )

        else:
            box = boxes[item["item"].pk]

            order_box = OrderBox.objects.create(
                order=order,
                box=box,
                name_ar=box.name_ar,
                name_en=box.name_en,
                sku=box.sku,
                quantity=quantity,
                price=get_effective_price(box, at=pricing_at),
            )

            for box_item in box_items_by_box[box.pk]:
                variant = variants[box_item.variant_id]
                product = products[variant.product_id]

                OrderBoxItem.objects.create(
                    order_box=order_box,
                    variant=variant,
                    sku=variant.sku,
                    product_name_ar=product.name_ar,
                    product_name_en=product.name_en,
                    quantity=box_item.quantity,
                )

    for variant_id, quantity in variant_quantities.items():
        variant = variants[variant_id]
        variant.stock -= quantity
        variant.save(update_fields=["stock", "updated_at"])

    for box_id, quantity in box_quantities.items():
        box = boxes[box_id]
        box.stock -= quantity
        box.save(update_fields=["stock", "updated_at"])

    transaction.on_commit(cart.clear)

    return order


@transaction.atomic
def cancel_order(*, order_id):
    order = Order.objects.select_for_update().get(pk=order_id)

    if order.stock_restored_at is not None:
        return order

    if order.status != "pending":
        raise ValueError("Only pending orders can be cancelled")

    variant_quantities = defaultdict(int)
    box_quantities = defaultdict(int)

    for item in order.items.all():
        variant_quantities[item.variant_id] += item.quantity

    order_boxes = order.boxes.prefetch_related("items")

    for order_box in order_boxes:
        box_quantities[order_box.box_id] += order_box.quantity

        for item in order_box.items.all():
            variant_quantities[item.variant_id] += (
                item.quantity * order_box.quantity
            )

    boxes = {
        box.pk: box
        for box in Box.objects.select_for_update()
        .filter(pk__in=box_quantities)
        .order_by("pk")
    }

    variants = {
        variant.pk: variant
        for variant in ProductVariant.objects.select_for_update()
        .filter(pk__in=variant_quantities)
        .order_by("pk")
    }

    if len(boxes) != len(box_quantities):
        raise ValueError("An ordered box no longer exists")

    if len(variants) != len(variant_quantities):
        raise ValueError("An ordered variant no longer exists")

    for variant_id, quantity in variant_quantities.items():
        variant = variants[variant_id]
        variant.stock += quantity
        variant.save(update_fields=["stock", "updated_at"])

    for box_id, quantity in box_quantities.items():
        box = boxes[box_id]
        box.stock += quantity
        box.save(update_fields=["stock", "updated_at"])

    order.status = "cancelled"
    order.stock_restored_at = timezone.now()
    order.save(update_fields=[
        "status",
        "stock_restored_at",
        "updated_at",
    ])

    return order