from decimal import Decimal
from datetime import datetime
from datetime import timedelta

from django.db.models import (
    Count,
    DecimalField,
    F,
    Sum,
)
from django.contrib.auth import get_user_model
from django.db.models.functions import TruncDate
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from brandat_egy.models import (
    Order,
    OrderItem,
    OrderBox,
    Product,
)


LOW_STOCK_THRESHOLD = 5


def calculate_revenue(queryset):
    result = queryset.aggregate(
        revenue=Sum(
            F("price") * F("quantity"),
            output_field=DecimalField(
                max_digits=18,
                decimal_places=2,
            ),
        )
    )

    return result["revenue"] or Decimal("0.00")


def dashboard_callback(request, context):
    user = request.user

    can_view_orders = user.has_perm(
        "brandat_egy.view_order"
    )
    can_view_products = user.has_perm(
        "brandat_egy.view_product"
    )

    context.update({
        "can_view_orders": can_view_orders,
        "can_view_products": can_view_products,
    })

    if can_view_orders:
        product_revenue = calculate_revenue(
            OrderItem.objects.filter(
                order__status="delivered"
            )
        )

        box_revenue = calculate_revenue(
            OrderBox.objects.filter(
                order__status="delivered"
            )
        )

        shipping_revenue = Order.objects.filter(
            status="delivered"
        ).aggregate(total=Sum("shipping_fee"))["total"] or Decimal("0.00")

        context.update({
            "delivered_sales": (
                product_revenue + box_revenue + shipping_revenue
            ),
            "pending_orders": Order.objects.filter(
                status__in=["confirmed", "pending"]
            ).count(),
            "shipped_orders": Order.objects.filter(
                status="shipped"
            ).count(),
        })



        period_start, period_end, range_key = _dashboard_range(request)
        context["selected_sales_period"] = range_key
        context["range_start"] = period_start
        context["range_end"] = period_end
        context["range_label"] = _range_label(period_start, period_end, range_key)

        (
            context["sales_chart"],
            context["period_sales"],
        ) = get_sales_chart_data(
            start_date=period_start,
            end_date=period_end,
        )

        (
            context["order_status_summary"],
            context["order_status_total"],
        ) = get_order_status_chart_data()

        context["home"] = get_home_kpis(
            delivered_sales=context["delivered_sales"]
        )
        context["top_products"] = get_top_products(
            start_date=period_start,
            end_date=period_end,
        )
        context["recent_orders"] = (
            Order.objects
            .prefetch_related("items", "boxes")
            .order_by("-created_at", "-pk")[:6]
        )
        (
            context["status_gradient"],
            context["order_status_legend"],
        ) = status_donut(
            context["order_status_summary"],
            context["order_status_total"],
        )
        context["status_legend"] = design_status_legend(
            context["order_status_summary"],
            context["order_status_total"],
        )
        context["sales_labels"] = [
            point["chart_label"] for point in context["sales_chart"]["points"]
        ]
        context["sales_values"] = [
            point["amount"] for point in context["sales_chart"]["points"]
        ]
        context["revenue_display"] = _plain_amount(
            context["delivered_sales"]
        )


    if can_view_products:
        context["low_stock_count"] = (
            Product.objects.filter(
                is_available=True,
                variants__is_active=True,
                variants__stock__lte=LOW_STOCK_THRESHOLD,
            )
            .distinct()
            .count()
        )

    return context



def _shift_percent(current, previous):
    current = Decimal(current)
    previous = Decimal(previous)
    if previous == 0:
        return None
    return int(
        ((current - previous) / previous * 100).quantize(Decimal("1"))
    )


def _revenue_between(start, end):
    total = Decimal("0.00")
    for model in (OrderItem, OrderBox):
        total += calculate_revenue(
            model.objects.filter(
                order__status="delivered",
                order__created_at__date__gte=start,
                order__created_at__date__lte=end,
            )
        )
    shipping = Order.objects.filter(
        status="delivered",
        created_at__date__gte=start,
        created_at__date__lte=end,
    ).aggregate(total=Sum("shipping_fee"))["total"] or Decimal("0.00")
    return total + shipping


def get_home_kpis(*, delivered_sales):
    today = timezone.localdate()
    current_start = today - timedelta(days=29)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=29)
    User = get_user_model()
    customers = User.objects.filter(is_staff=False, is_superuser=False)

    revenue_now = _revenue_between(current_start, today)
    revenue_prev = _revenue_between(previous_start, previous_end)
    delivered_count = Order.objects.filter(status="delivered").count()
    delivered_now = Order.objects.filter(
        status="delivered",
        created_at__date__gte=current_start,
        created_at__date__lte=today,
    ).count()
    delivered_prev = Order.objects.filter(
        status="delivered",
        created_at__date__gte=previous_start,
        created_at__date__lte=previous_end,
    ).count()
    aov = (
        delivered_sales / delivered_count
        if delivered_count
        else Decimal("0.00")
    )
    aov_now = revenue_now / delivered_now if delivered_now else Decimal("0.00")
    aov_prev = (
        revenue_prev / delivered_prev if delivered_prev else Decimal("0.00")
    )
    customers_now = customers.filter(
        date_joined__date__gte=current_start,
        date_joined__date__lte=today,
    ).count()
    customers_prev = customers.filter(
        date_joined__date__gte=previous_start,
        date_joined__date__lte=previous_end,
    ).count()
    orders_now = Order.objects.filter(
        created_at__date__gte=current_start,
        created_at__date__lte=today,
    ).count()
    orders_prev = Order.objects.filter(
        created_at__date__gte=previous_start,
        created_at__date__lte=previous_end,
    ).count()

    return {
        "revenue_change": _shift_percent(revenue_now, revenue_prev),
        "orders_total": Order.objects.count(),
        "orders_change": _shift_percent(orders_now, orders_prev),
        "customers_new": customers_now,
        "customers_change": _shift_percent(customers_now, customers_prev),
        "aov_display": _plain_amount(aov),
        "aov_change": _shift_percent(aov_now, aov_prev),
    }


def _parse_dashboard_day(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _dashboard_range(request):
    today = timezone.localdate()
    period = request.GET.get("period") or "30"
    if period == "today":
        return today, today, "today"
    if period == "yesterday":
        day = today - timedelta(days=1)
        return day, day, "yesterday"
    if period == "custom":
        start = _parse_dashboard_day(request.GET.get("start")) or today
        end = _parse_dashboard_day(request.GET.get("end")) or today
        if end < start:
            start, end = end, start
        return start, end, "custom"
    days = {"7": 7, "30": 30, "90": 90}.get(period, 30)
    return today - timedelta(days=days - 1), today, period


def _range_label(start, end, key):
    if key == "today":
        return "اليوم"
    if key == "yesterday":
        return "أمس"
    return f"{date_format(start, 'j F Y')} - {date_format(end, 'j F Y')}"


def get_top_products(limit=5, start_date=None, end_date=None):
    sold = OrderItem.objects.filter(order__status="delivered")
    if start_date is not None:
        sold = sold.filter(order__created_at__date__gte=start_date)
    if end_date is not None:
        sold = sold.filter(order__created_at__date__lte=end_date)
    rows = (
        sold
        .values("variant__product_id")
        .annotate(
            sold=Sum("quantity"),
            revenue=Sum(
                F("price") * F("quantity"),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            ),
        )
        .order_by("-revenue")[:limit]
    )
    ids = [
        row["variant__product_id"]
        for row in rows
        if row["variant__product_id"]
    ]
    products = {
        product.pk: product
        for product in Product.objects.filter(pk__in=ids).prefetch_related(
            "images"
        )
    }
    result = []
    for row in rows:
        product = products.get(row["variant__product_id"])
        if product is None:
            continue
        image = next(
            (item for item in product.images.all() if item.is_main),
            None,
        ) or next(iter(product.images.all()), None)
        result.append({
            "name": product.name_ar,
            "sold": row["sold"] or 0,
            "revenue": _plain_amount(row["revenue"] or 0),
            "image_url": image.image.url if image and image.image else "",
            "letter": (product.name_ar or "?")[:1],
            "url": reverse(
                "admin:brandat_egy_product_change",
                args=[product.pk],
            ),
        })
    return result


def design_status_legend(summary, total):
    names = {
        "delivered": _("Delivered"),
        "confirmed": _("Confirmed"),
        "preparing": _("Preparing"),
        "pending": _("Pending"),
        "shipped": _("Shipped"),
        "cancelled": _("Cancelled"),
        "paid": _("Paid"),
    }
    colors = {
        "delivered": "#6B1E2E",
        "confirmed": "#F0A3B6",
        "preparing": "#E7C2CE",
        "pending": "#F0A3B6",
        "shipped": "#F7C9D2",
        "cancelled": "#F3E6E8",
        "paid": "#E4D0D6",
    }
    by_code = {item["code"]: item["count"] for item in summary}
    legend = []
    for code in ("delivered", "confirmed", "preparing", "shipped", "cancelled"):
        count = by_code.get(code, 0)
        legend.append({
            "code": code,
            "label": names[code],
            "count": count,
            "percent": round(count / total * 100) if total else 0,
            "color": colors[code],
        })
    if by_code.get("paid"):
        count = by_code["paid"]
        legend.append({
            "code": "paid",
            "label": names["paid"],
            "count": count,
            "percent": round(count / total * 100) if total else 0,
            "color": colors["paid"],
        })
    return legend


def status_donut(summary, total):
    if not total:
        return "#E7E0DE 0% 100%", []
    cursor = 0
    parts = []
    legend = []
    for item in summary:
        if not item["count"]:
            legend.append({**item, "percent": 0})
            continue
        percent = item["count"] / total * 100
        end = cursor + percent
        parts.append(f"{item['color']} {cursor:.2f}% {end:.2f}%")
        legend.append({**item, "percent": round(percent)})
        cursor = end
    if not parts:
        return "#E7E0DE 0% 100%", legend
    return ", ".join(parts), legend


def get_sales_chart_data(days_count=30, start_date=None, end_date=None):
    today = timezone.localdate()
    if end_date is None:
        end_date = today
    if start_date is None:
        start_date = end_date - timedelta(days=days_count - 1)

    days = []
    cursor = start_date
    while cursor <= end_date:
        days.append(cursor)
        cursor += timedelta(days=1)
    days_count = max(len(days), 1)

    daily_sales = {
        day: Decimal("0.00")
        for day in days
    }

    for model in (OrderItem, OrderBox):
        sales = (
            model.objects
            .filter(
                order__status="delivered",
                order__created_at__date__gte=start_date,
                order__created_at__date__lte=end_date,
            )
            .order_by()
            .annotate(
                day=TruncDate("order__created_at")
            )
            .values("day")
            .annotate(
                total=Sum(
                    F("price") * F("quantity"),
                    output_field=DecimalField(
                        max_digits=18,
                        decimal_places=2,
                    ),
                )
            )
        )

        for sale in sales:
            day = sale["day"]

            if day in daily_sales:
                daily_sales[day] += (
                    sale["total"] or Decimal("0.00")
                )

    peak = max(daily_sales.values(), default=Decimal("0.00"))
    if days_count <= 7:
        label_step = 1
    elif days_count <= 30:
        label_step = 5
    else:
        label_step = 15

    points = []
    last_index = len(days) - 1
    for index, day in enumerate(days):
        amount = daily_sales[day]
        if amount > 0 and peak > 0:
            height = max(8, round(amount / peak * 100))
        else:
            height = 0
        x = round(index / last_index * 100, 2) if last_index else 0
        points.append({
            "label": day.strftime("%d/%m"),
            "chart_label": date_format(day, "j M"),
            "amount": float(amount),
            "amount_display": _plain_amount(amount),
            "height": int(height),
            "x": x,
            "y": 100 - int(height),
            "show_label": (
                index % label_step == 0 or index == last_index
            ),
        })

    period_sales = sum(
        daily_sales.values(),
        Decimal("0.00"),
    )

    line = " ".join(f"{point['x']},{point['y']}" for point in points)
    return (
        {
            "points": points,
            "line": line,
            "area": f"{line} 100,100 0,100",
            "peak_display": _plain_amount(peak),
            "mid_display": _plain_amount(peak / 2),
            "has_sales": peak > 0,
            "columns_class": f"brandat-sales-columns--{days_count}",
        },
        period_sales,
    )



def get_order_status_chart_data():
    # Count orders grouped by status.
    counts = {
        row["status"]: row["total"]
        for row in (
            Order.objects
            .values("status")
            .annotate(total=Count("pk"))
        )
    }

    # Each status has its own chart color.
    status_colors = [
        ("delivered", "#2F9D62"),
        ("confirmed", "#E39A45"),
        ("preparing", "#9E1D3F"),
        ("shipped", "#3B82C4"),
        ("cancelled", "#E15B6A"),
    ]

    # Include legacy paid orders when present.
    if counts.get("paid", 0) > 0:
        status_colors.append(
            ("paid", "#66589E")
        )

    # Use the translated model choices.
    status_labels = dict(Order.STATUS_CHOICES)

    summary = [
        {
            "code": code,
            "label": str(
                status_labels.get(code, code)
            ),
            "count": counts.get(code, 0),
            "color": color,
        }
        for code, color in status_colors
    ]

    return (
        summary,
        sum(item["count"] for item in summary),
    )


def _plain_amount(amount):
    amount = Decimal(amount).quantize(Decimal("0.01"))
    if amount == amount.to_integral():
        return f"{int(amount):,}"
    return f"{amount:,.2f}"
