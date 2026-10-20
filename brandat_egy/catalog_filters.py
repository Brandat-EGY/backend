
from collections import defaultdict

from django.db.models import F

from .models import Category


def get_category_subtree_ids(slug):
    categories = list(
        Category.objects.filter(
            is_active=True
        ).values(
            "id",
            "parent_id",
            "slug",
        )
    )

    by_id = {
        category["id"]: category
        for category in categories
    }

    target = next(
        (
            category
            for category in categories
            if category["slug"] == slug
        ),
        None,
    )

    if target is None:
        return []

    # Ensure the category has an active ancestor chain.
    current_id = target["id"]
    visited_ancestors = set()

    while current_id is not None:
        if current_id in visited_ancestors:
            return []

        visited_ancestors.add(current_id)

        category = by_id.get(current_id)

        if category is None:
            return []

        current_id = category["parent_id"]

    children_map = defaultdict(list)

    for category in categories:
        children_map[
            category["parent_id"]
        ].append(category["id"])

    # Collect the category and all active descendants.
    result_ids = set()
    stack = [target["id"]]

    while stack:
        category_id = stack.pop()

        if category_id in result_ids:
            continue

        result_ids.add(category_id)

        stack.extend(
            children_map.get(category_id, [])
        )

    return list(result_ids)


def apply_catalog_filters(queryset, filters):
    brand_slugs = filters.get("brand")

    if brand_slugs:
        queryset = queryset.filter(
            brand__slug__in=brand_slugs,
            brand__is_active=True,
        )

    category_slug = filters.get("category")

    if category_slug:
        category_ids = get_category_subtree_ids(
            category_slug
        )

        queryset = queryset.filter(
            category_id__in=category_ids
        )

    min_price = filters.get("min_price")

    if min_price is not None:
        queryset = queryset.filter(
            starting_price__gte=min_price
        )

    max_price = filters.get("max_price")

    if max_price is not None:
        queryset = queryset.filter(
            starting_price__lte=max_price
        )

    ordering = filters["ordering"]


    if ordering == "relevance":
        return queryset.order_by(
            "-search_score",
            "-created_at",
            "-pk",
        )
    
    if ordering == "price_asc":
        return queryset.order_by(
            F("starting_price").asc(nulls_last=True),
            "-pk",
        )

    if ordering == "price_desc":
        return queryset.order_by(
            F("starting_price").desc(nulls_last=True),
            "-pk",
        )

    if ordering == "brand_az":
        return queryset.order_by(
            F("brand__name_en").asc(nulls_last=True),
            "-pk",
        )

    if ordering == "category_az":
        return queryset.order_by(
            F("category__name_en").asc(nulls_last=True),
            "-pk",
        )

    return queryset.order_by(
        "-created_at",
        "-pk",
    )
