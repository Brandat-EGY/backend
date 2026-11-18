from urllib.parse import urlparse

from django import forms
from django.contrib import admin
from django.forms.models import BaseInlineFormSet
from django.contrib.admin.models import LogEntry
from django.contrib.admin.utils import unquote
from django.contrib.admin.views.main import ChangeList
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
import csv
from datetime import datetime
from decimal import Decimal

from django.db.models import Count
from django.db.models import Prefetch
from django.db.models import DecimalField
from django.db.models import ExpressionWrapper
from django.db.models import F
from django.db.models import Q
from django.db.models import Sum
from django.utils import timezone
from django.utils.formats import date_format
from django.http import Http404
from django.http import HttpResponse
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import path
from django.urls import reverse
from django.template.loader import get_template
from django.utils.html import format_html
from django.utils.html import format_html_join
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.admin import TabularInline

from datetime import timedelta
from core.dashboard import LOW_STOCK_THRESHOLD
from core.dashboard import _dashboard_range
from core.dashboard import _range_label
from core.dashboard import _revenue_between
from core.dashboard import get_top_products
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
    Favorite,
    ShippingRate,
)
from django.contrib import messages
from rest_framework_simplejwt.token_blacklist.models import (
    OutstandingToken,
    BlacklistedToken,
)
from .services import advance_order_status
from .services import cancel_order


# Register your models here.

class StoreAdmin(ModelAdmin):
    save_on_top = True

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(
            db_field,
            request,
            **kwargs,
        )
        if formfield is None:
            return formfield

        if db_field.name == "user":
            formfield.empty_label = _("No account")
        else:
            formfield.empty_label = _("Choose")

        return formfield


class ProductImageInline(TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "is_main")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "image":
            kwargs["widget"] = forms.FileInput(attrs={"accept": "image/*"})
        return super().formfield_for_dbfield(db_field, request, **kwargs)

class ProductVariantFormSet(BaseInlineFormSet):
    def __init__(
        self,
        data=None,
        files=None,
        instance=None,
        save_as_new=False,
        prefix=None,
        queryset=None,
        **kwargs,
    ):
        if data is not None and instance is not None and instance.pk and not save_as_new:
            prefix = self.get_default_prefix() if prefix is None else prefix
            source = self.model._default_manager if queryset is None else queryset
            existing = source.filter(**{self.fk.name: instance}).order_by("pk")
            data = data.copy()
            try:
                total = int(data.get(f"{prefix}-TOTAL_FORMS") or 0)
            except (TypeError, ValueError):
                total = 0
            pk_name = self.model._meta.pk.name
            slots = []
            for index, variant in enumerate(existing):
                if index >= total:
                    break
                slots.append((f"{prefix}-{index}-{pk_name}", variant.pk))
            if slots and all(not data.get(key) for key, _pk in slots):
                for key, pk in slots:
                    data[key] = str(pk)
        super().__init__(data, files, instance, save_as_new, prefix, queryset, **kwargs)


class ProductVariantInline(TabularInline):
    model = ProductVariant
    formset = ProductVariantFormSet
    template = "admin/brandat_egy/product_variant_inline.html"
    extra = 0
    fields = (
        "price",
        "discount_price",
        "size",
        "stock",
        "shade_ar",
        "shade_en",
        "is_active",
    )

    def get_extra(self, request, obj=None, **kwargs):
        if obj is None or not obj.variants.exists():
            return 1
        return 0

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "is_active" and formfield is not None:
            formfield.label = _("Shown for sale")
        return formfield


class LowStockFilter(admin.SimpleListFilter):
    title = _("Stock")
    parameter_name = "stock"

    def lookups(self, request, model_admin):
        return (("low", _("Running low")),)

    def queryset(self, request, queryset):
        if self.value() == "low":
            return queryset.filter(
                is_available=True,
                variants__is_active=True,
                variants__stock__lte=LOW_STOCK_THRESHOLD,
            ).distinct()
        return queryset


@admin.register(Product)
class ProductAdmin(StoreAdmin):
    list_display = (
        "product_summary",
        "brand_name",
        "selling_price",
        "stock_amount",
        "catalog_status",
        "visibility_switch",
    )
    list_display_links = ("product_summary",)
    list_filter = (LowStockFilter, "is_available", "category", "brand")
    list_before_template = "admin/brandat_egy/product_stats.html"
    change_list_template = "admin/brandat_egy/product_changelist.html"
    change_form_template = "admin/brandat_egy/product_change.html"
    list_fullwidth = True
    list_per_page = 20
    ordering = ("-created_at",)
    search_fields = ("name_ar", "name_en", "description_ar", "description_en")
    inlines = (ProductImageInline, ProductVariantInline)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("category", "brand")
            .prefetch_related("images", "variants")
        )

    def get_urls(self):
        return [
            path(
                "<path:object_id>/toggle-available/",
                self.admin_site.admin_view(self.toggle_available),
                name="brandat_egy_product_toggle_available",
            ),
        ] + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        self.request = request
        extra_context = extra_context or {}
        extra_context["product_stats"] = self.product_stats()
        return super().changelist_view(request, extra_context)

    def product_stats(self):
        sold = (
            OrderItem.objects.aggregate(total=Sum("quantity"))["total"]
            or 0
        )
        return {
            "active": Product.objects.filter(is_available=True).count(),
            "total": Product.objects.count(),
            "low": (
                Product.objects.filter(
                    is_available=True,
                    variants__is_active=True,
                    variants__stock__lte=LOW_STOCK_THRESHOLD,
                )
                .distinct()
                .count()
            ),
            "sold": sold,
        }

    def toggle_available(self, request, object_id):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])

        product = self.get_object(request, unquote(object_id))
        if product is None:
            return redirect("admin:brandat_egy_product_changelist")
        if not self.has_change_permission(request, product):
            raise PermissionDenied

        product.is_available = not product.is_available
        product.save(update_fields=["is_available", "updated_at"])
        return redirect(
            request.META.get("HTTP_REFERER")
            or reverse("admin:brandat_egy_product_changelist")
        )

    @admin.display(description=_("Product"))
    def product_summary(self, obj):
        image = next(
            (item for item in obj.images.all() if item.is_main),
            None,
        ) or next(iter(obj.images.all()), None)
        details = obj.category.name_ar if obj.category_id else ""
        if image and image.image:
            thumb = format_html(
                '<img class="brandat-product-thumb" src="{}" alt="">',
                image.image.url,
            )
        else:
            thumb = format_html(
                '<span class="brandat-product-thumb brandat-product-thumb--empty">{}</span>',
                (obj.name_ar or "?")[:1],
            )
        return format_html(
            '<div class="brandat-product-cell">{}<div><strong>{}</strong><small>{}</small></div></div>',
            thumb,
            obj.name_ar,
            details,
        )

    @admin.display(description=_("Brand"), ordering="brand__name_ar")
    def brand_name(self, obj):
        if obj.brand_id:
            return obj.brand.name_ar
        return "—"

    @admin.display(description=_("Pieces in stock"))
    def stock_amount(self, obj):
        return sum(variant.stock for variant in obj.variants.all())

    @admin.display(description=_("Status"))
    def catalog_status(self, obj):
        stock = sum(
            variant.stock
            for variant in obj.variants.all()
            if variant.is_active
        )
        if not obj.is_available or stock <= 0:
            code, label = "out", _("Out of stock")
        elif stock <= LOW_STOCK_THRESHOLD:
            code, label = "low", _("Running low")
        else:
            code, label = "active", _("In stock")
        return format_html(
            '<span class="bd-pill bd-pill--{}">{}</span>',
            code,
            label,
        )

    @admin.display(description=_("Price"))
    def selling_price(self, obj):
        prices = [
            variant.price
            for variant in obj.variants.all()
            if variant.is_active
        ]
        if not prices:
            return "—"
        lowest = min(prices)
        if len(prices) == 1:
            return format_html("{} {}", f"{lowest:.2f}", _("EGP"))
        return format_html(
            "{} {} {}",
            _("From"),
            f"{lowest:.2f}",
            _("EGP"),
        )

    @admin.display(description=_("Visible"))
    def visibility_switch(self, obj):
        if not hasattr(self, "request") or not self.has_change_permission(
            self.request,
            obj,
        ):
            return _("Visible") if obj.is_available else _("Hidden")

        from django.middleware.csrf import get_token

        return format_html(
            '<form method="post" action="{}" class="brandat-visibility-form">'
            '<input type="hidden" name="csrfmiddlewaretoken" value="{}">'
            '<button type="submit" data-testid="product-visibility-{}" '
            'class="brandat-visibility {}" aria-pressed="{}">'
            '<span></span></button></form>',
            reverse(
                "admin:brandat_egy_product_toggle_available",
                args=[obj.pk],
            ),
            get_token(self.request),
            obj.pk,
            "is-on" if obj.is_available else "",
            "true" if obj.is_available else "false",
        )
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in {"description_ar", "description_en"}:
            kwargs["widget"] = forms.Textarea(attrs={"rows": 8, "class": "product-description"})
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    fieldsets = (
        (
            _("Product names"),
            {"fields": (("name_ar", "name_en"),)},
        ),
        (
            _("Product story"),
            {"fields": ("description_ar", "description_en")},
        ),
        (
            _("Where it appears"),
            {
                "description": _(
                    "Choose the category and brand, and leave the barcode empty if you do not have it."
                ),
                "fields": (
                    ("category", "brand"),
                    "is_available",
                    "scanned_code",
                ),
            },
        ),
    )

class OrderItemInline(TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ("variant", "quantity", "price")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

class OrderBoxInline(TabularInline):
    model = OrderBox
    extra = 0
    can_delete = False
    show_change_link = False

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

    def has_change_permission(self, request, obj=None):
        return False

@admin.register(Order)
class OrderAdmin(StoreAdmin):
    list_display = (
        "id",
        "customer_cell",
        "ordered_on",
        "status_badge",
        "order_total",
        "list_actions",
    )
    list_filter = ("status",)
    list_before_template = "admin/brandat_egy/order_tabs.html"
    change_list_template = "admin/brandat_egy/order_changelist.html"
    change_form_template = "admin/brandat_egy/order_change.html"
    list_fullwidth = True
    list_per_page = 20
    search_fields = ("customer_name", "phone", "email", "address")
    readonly_fields = (
        "customer_name",
        "phone",
        "email",
        "address",
        "status",
        "status_badge",
        "total_price",
        "order_contents",
        "cod_actions",
        "user",
        "session_key",
        "stock_restored_at",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (
            _("Delivery details"),
            {
                "description": _(
                    "The order comes from the website, so these details stay as the customer wrote them."
                ),
                "fields": (
                    ("customer_name", "phone"),
                    "email",
                    "address",
                ),
            },
        ),
        (
            _("Order contents"),
            {"fields": ("order_contents",)},
        ),
        (
            _("Order follow-up"),
            {
                "description": _(
                    "Cash is collected on delivery. Send the order out, then mark it received after the customer pays. Cancel only while it is still waiting, and the pieces go back."
                ),
                "fields": (
                    ("status_badge", "total_price"),
                    "cod_actions",
                    ("created_at", "updated_at"),
                ),
            },
        ),
        (
            _("Internal details"),
            {
                "classes": ("collapse",),
                "description": _("Only needed if something looks wrong."),
                "fields": ("user", "session_key", "stock_restored_at"),
            },
        ),
    )

    actions = ("cancel_selected_orders",)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("governorate")
            .prefetch_related(
                Prefetch(
                    "items__variant__product__images",
                    queryset=ProductImage.objects.order_by("-is_main", "pk"),
                ),
                Prefetch(
                    "boxes__box__images",
                    queryset=BoxImage.objects.order_by("-is_main", "pk"),
                ),
                Prefetch(
                    "boxes__items__variant__product__images",
                    queryset=ProductImage.objects.order_by("-is_main", "pk"),
                ),
            )
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        order = self.get_object(request, unquote(object_id))
        if order is not None:
            extra_context["customer_stats"] = self.customer_stats(order)
            extra_context["order_steps"] = self.order_steps(order)
        return super().change_view(request, object_id, form_url, extra_context)

    def customer_stats(self, order):
        if order.user_id:
            orders = Order.objects.filter(user_id=order.user_id)
            since = order.user.date_joined
            registered = True
        else:
            orders = Order.objects.filter(user__isnull=True, phone=order.phone)
            since = orders.order_by("created_at").values_list("created_at", flat=True).first()
            registered = False
        delivered = orders.filter(status="delivered")
        line = ExpressionWrapper(
            F("price") * F("quantity"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        items_total = (
            OrderItem.objects.filter(order__in=delivered).aggregate(total=Sum(line))["total"]
            or Decimal("0")
        )
        boxes_total = (
            OrderBox.objects.filter(order__in=delivered).aggregate(total=Sum(line))["total"]
            or Decimal("0")
        )
        shipping_total = delivered.aggregate(total=Sum("shipping_fee"))["total"] or Decimal("0")
        return {
            "registered": registered,
            "since": since,
            "orders": orders.count(),
            "spent": items_total + boxes_total + shipping_total,
        }

    def order_steps(self, order):
        rank = {
            "pending": 0,
            "confirmed": 0,
            "preparing": 1,
            "shipped": 2,
            "delivered": 3,
            "paid": 3,
        }.get(order.status, 0)
        if order.status == "cancelled":
            return [{
                "label": "تم إلغاء الطلب وإرجاع القطع",
                "at": order.updated_at,
                "done": True,
            }]
        labels = (
            "تم تأكيد الطلب",
            "جاري التجهيز",
            "خرج للتوصيل",
            "تم التسليم والتحصيل",
        )
        steps = []
        for index, label in enumerate(labels):
            done = rank >= index
            when = None
            if done and index == 0:
                when = order.created_at
            elif done and index == rank:
                when = order.updated_at
            steps.append({"label": label, "at": when, "done": done})
        return steps

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        counts = {
            row["status"]: row["total"]
            for row in Order.objects.values("status").annotate(total=Count("pk"))
        }
        extra_context["order_tab_counts"] = {
            "all": sum(counts.values()),
            "confirmed": counts.get("confirmed", 0),
            "preparing": counts.get("preparing", 0),
            "pending": counts.get("pending", 0),
            "shipped": counts.get("shipped", 0),
            "delivered": counts.get("delivered", 0),
            "cancelled": counts.get("cancelled", 0),
        }
        return super().changelist_view(request, extra_context)

    @admin.display(description=_("Customer"))
    def customer_cell(self, obj):
        letter = (obj.customer_name or "?")[:1]
        return format_html(
            '<span class="bd-person"><span class="bd-avatar">{}</span><span>{}</span></span>',
            letter,
            obj.customer_name,
        )

    @admin.display(description=_("Date"), ordering="created_at")
    def ordered_on(self, obj):
        return date_format(timezone.localtime(obj.created_at), "DATE_FORMAT")

    @admin.action(
        description=_("Cancel selected pending orders"),
        permissions=["view"],
    )
    def cancel_selected_orders(self, request, queryset):
        cancelled_count = 0

        for order in queryset.order_by("pk"):
            previous_status = order.status
            try:
                result = cancel_order(order_id=order.pk)
            except ValueError as error:
                self.message_user(
                    request,
                    gettext("Order #%(number)s: %(error)s")
                    % {"number": order.pk, "error": error},
                    level=messages.WARNING,
                )
            else:
                if previous_status in {"pending", "confirmed", "preparing", "shipped"} and result.status == "cancelled":
                    cancelled_count += 1

        if cancelled_count:
            self.message_user(
                request,
                gettext("%(count)s orders cancelled and stock restored.")
                % {"count": cancelled_count},
                level=messages.SUCCESS,
            )

    def get_urls(self):
        return [
            path(
                "<path:object_id>/step/<str:step>/",
                self.admin_site.admin_view(self.order_step),
                name="brandat_egy_order_step",
            ),
        ] + super().get_urls()

    def order_step(self, request, object_id, step):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if step not in {"prepare", "ship", "deliver", "cancel"}:
            raise Http404

        order = self.get_object(request, unquote(object_id))
        if order is None:
            return redirect("admin:brandat_egy_order_changelist")
        if not self.has_view_permission(request, order):
            raise PermissionDenied

        previous_status = order.status
        try:
            if step == "cancel":
                order = cancel_order(order_id=order.pk)
            elif step == "prepare":
                order = advance_order_status(
                    order_id=order.pk,
                    new_status="preparing",
                )
            elif step == "ship":
                order = advance_order_status(
                    order_id=order.pk,
                    new_status="shipped",
                )
            else:
                order = advance_order_status(
                    order_id=order.pk,
                    new_status="delivered",
                )
        except ValueError as error:
            self.message_user(request, str(error), level=messages.WARNING)
        else:
            changed = order.status != previous_status
            if step == "cancel" and changed:
                self.message_user(
                    request,
                    gettext(
                        "The order was cancelled and the pieces went back to stock."
                    ),
                    level=messages.SUCCESS,
                )
            elif step == "prepare" and changed:
                self.message_user(
                    request,
                    gettext("The order is being prepared."),
                    level=messages.SUCCESS,
                )
            elif step == "ship" and changed:
                self.message_user(
                    request,
                    gettext(
                        "The order is out for delivery. Collect the cash when it arrives."
                    ),
                    level=messages.SUCCESS,
                )
            elif step == "deliver" and changed:
                self.message_user(
                    request,
                    gettext("Marked as received and paid on delivery."),
                    level=messages.SUCCESS,
                )
            elif step == "cancel":
                self.message_user(
                    request,
                    gettext("This order was already cancelled."),
                    level=messages.WARNING,
                )
            else:
                self.message_user(
                    request,
                    gettext("This order was already updated."),
                    level=messages.WARNING,
                )
            if changed:
                self.log_change(
                    request,
                    order,
                    gettext("Order status updated."),
                )

        return self._redirect_back(request, order)

    def _redirect_back(self, request, order):
        referer = request.META.get("HTTP_REFERER", "")
        parsed = urlparse(referer)
        if (
            parsed.scheme in {"http", "https"}
            and parsed.netloc == request.get_host()
        ):
            return redirect(referer)
        return redirect("admin:brandat_egy_order_change", order.pk)

    @admin.display(description=_("Address"))
    def delivery_address(self, obj):
        text = (obj.address or "").strip()
        if not text:
            return "—"
        short = text if len(text) <= 42 else f"{text[:42]}…"
        return format_html(
            '<span class="brandat-address" title="{}">{}</span>',
            text,
            short,
        )

    @admin.display(description=_("Order contents"))
    def order_contents(self, obj):
        rows = []
        for item in obj.items.all():
            variant = item.variant
            rows.append((
                gettext("Product line"),
                variant.product.name_ar,
                variant.sku,
                item.quantity,
                f"{item.price:.2f}",
                f"{item.total_price:.2f}",
            ))
        for box in obj.boxes.all():
            rows.append((
                gettext("Box line"),
                box.name_ar,
                box.sku,
                box.quantity,
                f"{box.price:.2f}",
                f"{box.total_price:.2f}",
            ))
        if not rows:
            return gettext("This order has no items.")
        body = format_html_join(
            "",
            (
                "<tr><td><span class=\"brandat-line-kind\">{}</span></td>"
                "<td><strong>{}</strong><small>{}</small></td>"
                "<td>{}</td><td>{}</td><td>{}</td></tr>"
            ),
            rows,
        )
        return format_html(
            '<table class="brandat-order-lines" data-testid="order-contents-{}">'
            "<thead><tr><th>{}</th><th>{}</th><th>{}</th><th>{}</th><th>{}</th></tr></thead>"
            "<tbody>{}</tbody></table>",
            obj.pk,
            gettext("Kind"),
            gettext("Piece"),
            gettext("Quantity"),
            gettext("Unit price"),
            gettext("Line total"),
            body,
        )

    @admin.display(description=_("Order total"))
    def order_total(self, obj):
        amount = obj.total_price.quantize(Decimal("0.01"))
        if amount == amount.to_integral():
            text = f"{int(amount):,}"
        else:
            text = f"{amount:,.2f}"
        return format_html("{} {}", text, gettext("EGP"))

    @admin.display(description=_("Order status"), ordering="status")
    def status_badge(self, obj):
        return format_html(
            '<span class="brandat-status brandat-status--{}" data-testid="order-status-{}">{}</span>',
            obj.status,
            obj.pk,
            obj.get_status_display(),
        )

    @admin.display(description=_("Next step"))
    def list_actions(self, obj):
        return self._order_actions(obj, include_note=False)

    @admin.display(description=_("Next step"))
    def cod_actions(self, obj):
        return self._order_actions(obj, include_note=True)

    def _order_actions(self, obj, *, include_note):
        steps = []
        note = ""
        if obj.status in {"pending", "confirmed"}:
            steps = [
                (
                    "prepare",
                    gettext("Start preparing"),
                    f"order-prepare-{obj.pk}",
                    gettext("Start preparing this order?"),
                    False,
                ),
                (
                    "cancel",
                    gettext("Cancel the order"),
                    f"order-cancel-{obj.pk}",
                    gettext("Cancel this order and put the pieces back?"),
                    True,
                ),
            ]
        elif obj.status == "preparing":
            steps = [
                (
                    "ship",
                    gettext("Send it out"),
                    f"order-ship-{obj.pk}",
                    gettext("Send this order out for delivery?"),
                    False,
                ),
                (
                    "cancel",
                    gettext("Cancel the order"),
                    f"order-cancel-{obj.pk}",
                    gettext("Cancel this order and put the pieces back?"),
                    True,
                ),
            ]
        elif obj.status == "shipped":
            steps = [
                (
                    "deliver",
                    gettext("Received and paid"),
                    f"order-deliver-{obj.pk}",
                    gettext("Did the customer receive it and pay?"),
                    False,
                ),
                (
                    "cancel",
                    gettext("Cancel the order"),
                    f"order-cancel-{obj.pk}",
                    gettext("Cancel this order and put the pieces back?"),
                    True,
                ),
            ]
        elif include_note and obj.status == "delivered":
            note = gettext("This order was received and the cash was collected.")
        elif include_note and obj.status == "cancelled":
            note = gettext("This order was cancelled and the pieces went back.")
        elif include_note:
            note = gettext("Nothing else to do on this order.")

        buttons = format_html_join(
            "",
            (
                '<button type="submit" formmethod="post" formnovalidate '
                'formaction="{}" class="brandat-order-step{}" '
                'data-testid="{}" onclick="return confirm(\'{}\')">{}</button>'
            ),
            (
                (
                    reverse(
                        "admin:brandat_egy_order_step",
                        args=[obj.pk, step],
                    ),
                    " brandat-order-step--cancel" if danger else "",
                    testid,
                    confirm,
                    label,
                )
                for step, label, testid, confirm, danger in steps
            ),
        )
        note_html = (
            format_html('<p class="brandat-order-note">{}</p>', note)
            if note
            else ""
        )
        return format_html(
            '<div class="brandat-order-steps" data-testid="order-actions-{}">{}{}</div>',
            obj.pk,
            buttons,
            note_html,
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        raise PermissionDenied

@admin.register(Review)
class ReviewAdmin(StoreAdmin):
    list_display = ("order_item", "order_box", "rating", "name", "created_at")
    list_filter = ("rating",)
    search_fields = ("name", "comment")
    readonly_fields = ("order_item", "order_box", "created_at")
    fieldsets = (
        (
            _("The review"),
            {
                "fields": (
                    "order_item",
                    "order_box",
                    ("name", "rating"),
                    "comment",
                    "created_at",
                ),
            },
        ),
    )

@admin.register(Category)
class CategoryAdmin(StoreAdmin):
    list_display = ("name_ar", "name_en", "parent", "is_active")
    list_filter = ("is_active", "parent")
    search_fields = ("name_ar", "name_en")
    fieldsets = (
        (
            _("Category names"),
            {
                "fields": (
                    ("name_ar", "name_en"),
                    "parent",
                    "is_active",
                ),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if not obj.slug:
            obj.slug = unique_slug(
                Category,
                arabic_to_slug(obj.name_ar) or slugify(obj.name_en or ""),
                obj,
                "category",
            )
        super().save_model(request, obj, form, change)


@admin.register(Brand)
class BrandAdmin(StoreAdmin):
    list_display = ("name_ar", "name_en", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name_ar", "name_en")
    fieldsets = (
        (
            _("Brand names"),
            {
                "fields": (
                    ("name_ar", "name_en"),
                    "is_active",
                ),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if not obj.slug:
            obj.slug = unique_slug(
                Brand,
                arabic_to_slug(obj.name_ar) or slugify(obj.name_en or ""),
                obj,
                "brand",
            )
        super().save_model(request, obj, form, change)



class BoxItemForm(forms.ModelForm):
    class Meta:
        model = BoxItem
        fields = ("variant", "quantity")
        widgets = {
            "variant": forms.HiddenInput(),
            "quantity": forms.NumberInput(attrs={
                "min": 1,
                "class": "box-qty",
            }),
        }


def box_variant_catalog():
    variants = (
        ProductVariant.objects
        .select_related("product")
        .prefetch_related("product__images")
        .order_by("product__name_ar", "size", "shade_ar", "pk")
    )
    rows = []
    for variant in variants:
        images = list(variant.product.images.all())
        image = next(
            (item for item in images if item.is_main and item.image),
            None,
        ) or next((item for item in images if item.image), None)
        detail = " · ".join(
            part for part in (variant.size, variant.shade_ar) if part
        )
        rows.append({
            "id": variant.pk,
            "product_id": variant.product_id,
            "url": reverse(
                "admin:brandat_egy_product_change",
                args=[variant.product_id],
            ),
            "name": variant.product.name_ar,
            "detail": detail,
            "price": f"{variant.price:.2f}",
            "stock": variant.stock,
            "image": image.image.url if image and image.image else "",
            "search": " ".join(
                part for part in (
                    variant.product.name_ar,
                    variant.product.name_en,
                    variant.product.scanned_code,
                    variant.size,
                    variant.shade_ar,
                    variant.shade_en,
                    variant.sku,
                ) if part
            ).casefold(),
        })
    return rows


class BoxItemInline(TabularInline):
    model = BoxItem
    form = BoxItemForm
    extra = 0
    fields = ("variant", "quantity")


class BoxImageInline(TabularInline):
    model = BoxImage
    extra = 1
    fields = ("image", "is_main")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "image":
            kwargs["widget"] = forms.FileInput(attrs={"accept": "image/*"})
        return super().formfield_for_dbfield(db_field, request, **kwargs)



@admin.register(Box)
class BoxAdmin(StoreAdmin):
    list_display = (
        "box_summary",
        "stock_amount",
        "selling_price",
        "catalog_status",
        "visibility_switch",
    )
    list_display_links = ("box_summary",)
    list_filter = ("is_active",)
    list_before_template = "admin/brandat_egy/box_stats.html"
    change_list_template = "admin/brandat_egy/box_changelist.html"
    change_form_template = "admin/brandat_egy/box_change.html"
    list_fullwidth = True
    list_per_page = 20
    ordering = ("-created_at",)
    search_fields = ("name_ar", "name_en", "sku")

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("images")

    def get_urls(self):
        return [
            path(
                "<path:object_id>/toggle-active/",
                self.admin_site.admin_view(self.toggle_active),
                name="brandat_egy_box_toggle_active",
            ),
        ] + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        self.request = request
        extra_context = extra_context or {}
        extra_context["box_stats"] = self.box_stats()
        return super().changelist_view(request, extra_context)

    def box_stats(self):
        sold = OrderBox.objects.aggregate(total=Sum("quantity"))["total"] or 0
        return {
            "active": Box.objects.filter(is_active=True).count(),
            "total": Box.objects.count(),
            "low": Box.objects.filter(
                is_active=True,
                stock__lte=LOW_STOCK_THRESHOLD,
            ).count(),
            "sold": sold,
        }

    def toggle_active(self, request, object_id):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        box = self.get_object(request, unquote(object_id))
        if box is None:
            return redirect("admin:brandat_egy_box_changelist")
        if not self.has_change_permission(request, box):
            raise PermissionDenied
        box.is_active = not box.is_active
        box.save(update_fields=["is_active", "updated_at"])
        return redirect(
            request.META.get("HTTP_REFERER")
            or reverse("admin:brandat_egy_box_changelist")
        )

    @admin.display(description=_("Box"))
    def box_summary(self, obj):
        image = next(
            (item for item in obj.images.all() if item.is_main),
            None,
        ) or next(iter(obj.images.all()), None)
        if image and image.image:
            thumb = format_html(
                '<img class="brandat-product-thumb" src="{}" alt="">',
                image.image.url,
            )
        else:
            thumb = format_html(
                '<span class="brandat-product-thumb brandat-product-thumb--empty">{}</span>',
                (obj.name_ar or "?")[:1],
            )
        return format_html(
            '<div class="brandat-product-cell">{}<div><strong>{}</strong><small>{}</small></div></div>',
            thumb,
            obj.name_ar,
            obj.sku,
        )

    @admin.display(description=_("Pieces in stock"), ordering="stock")
    def stock_amount(self, obj):
        return obj.stock

    @admin.display(description=_("Price"))
    def selling_price(self, obj):
        amount = obj.discount_price or obj.price
        if obj.discount_price:
            return format_html(
                '<span class="brandat-price">{} {} <small>{} {}</small></span>',
                f"{obj.discount_price:.2f}",
                _("EGP"),
                f"{obj.price:.2f}",
                _("EGP"),
            )
        return format_html("{} {}", f"{amount:.2f}", _("EGP"))

    @admin.display(description=_("Status"))
    def catalog_status(self, obj):
        if not obj.is_active or obj.stock <= 0:
            code, label = "out", _("Out of stock")
        elif obj.stock <= LOW_STOCK_THRESHOLD:
            code, label = "low", _("Running low")
        else:
            code, label = "active", _("In stock")
        return format_html(
            '<span class="bd-pill bd-pill--{}">{}</span>',
            code,
            label,
        )

    @admin.display(description=_("Visible"))
    def visibility_switch(self, obj):
        if not hasattr(self, "request") or not self.has_change_permission(
            self.request,
            obj,
        ):
            return _("Visible") if obj.is_active else _("Hidden")

        from django.middleware.csrf import get_token

        return format_html(
            '<form method="post" action="{}" class="brandat-visibility-form">'
            '<input type="hidden" name="csrfmiddlewaretoken" value="{}">'
            '<button type="submit" data-testid="box-visibility-{}" '
            'class="brandat-visibility {}" aria-pressed="{}">'
            '<span></span></button></form>',
            reverse(
                "admin:brandat_egy_box_toggle_active",
                args=[obj.pk],
            ),
            get_token(self.request),
            obj.pk,
            "is-on" if obj.is_active else "",
            "true" if obj.is_active else "false",
        )
    readonly_fields = ("created_at", "updated_at")
    inlines = (BoxItemInline, BoxImageInline)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["box_variant_catalog"] = box_variant_catalog()
        return super().changeform_view(
            request,
            object_id,
            form_url,
            extra_context,
        )

    def save_model(self, request, obj, form, change):
        if not obj.sku:
            obj.sku = unique_box_sku()
        super().save_model(request, obj, form, change)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in {"description_ar", "description_en"}:
            kwargs["widget"] = forms.Textarea(attrs={"rows": 3})
        return super().formfield_for_dbfield(db_field, request, **kwargs)
    fieldsets = (
        (
            _("Box names"),
            {"fields": (("name_ar", "name_en"),)},
        ),
        (
            _("Box story"),
            {"fields": ("description_ar", "description_en")},
        ),
        (
            _("Price and stock"),
            {
                "fields": (
                    ("price", "discount_price"),
                    ("stock", "is_active"),
                ),
            },
        ),
        (
            _("Record dates"),
            {"fields": (("created_at", "updated_at"),)},
        ),
    )


class OrderBoxItemInline(TabularInline):
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

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(OrderBox)
class OrderBoxAdmin(StoreAdmin):
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
    fieldsets = (
        (
            _("Saved box details"),
            {
                "fields": (
                    ("order", "box"),
                    ("name_ar", "name_en"),
                    "sku",
                ),
            },
        ),
        (
            _("Price and stock"),
            {
                "fields": (
                    ("quantity", "price"),
                    "total_price",
                ),
            },
        ),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        raise PermissionDenied


ARABIC_SLUG_LETTERS = {
    "ا": "a",
    "أ": "a",
    "إ": "e",
    "آ": "a",
    "ب": "b",
    "ت": "t",
    "ث": "th",
    "ج": "j",
    "ح": "h",
    "خ": "kh",
    "د": "d",
    "ذ": "dh",
    "ر": "r",
    "ز": "z",
    "س": "s",
    "ش": "sh",
    "ص": "s",
    "ض": "d",
    "ط": "t",
    "ظ": "z",
    "ع": "a",
    "غ": "gh",
    "ف": "f",
    "ق": "q",
    "ك": "k",
    "ل": "l",
    "م": "m",
    "ن": "n",
    "ه": "h",
    "ة": "h",
    "و": "o",
    "ؤ": "w",
    "ي": "y",
    "ى": "a",
    "ئ": "y",
    "ء": "",
    "٠": "0",
    "١": "1",
    "٢": "2",
    "٣": "3",
    "٤": "4",
    "٥": "5",
    "٦": "6",
    "٧": "7",
    "٨": "8",
    "٩": "9",
}


def arabic_to_slug(name):
    letters = []
    for char in name or "":
        if char in ARABIC_SLUG_LETTERS:
            letters.append(ARABIC_SLUG_LETTERS[char])
        elif char.isascii():
            letters.append(char)
    return slugify("".join(letters))[:180]


def unique_slug(model, base, instance, fallback):
    slug = (base or fallback)[:150]
    candidate = slug
    number = 2
    taken = model.objects.all()
    if getattr(instance, "pk", None):
        taken = taken.exclude(pk=instance.pk)
    while taken.filter(slug=candidate).exists():
        suffix = f"-{number}"
        candidate = f"{slug[:160 - len(suffix)]}{suffix}"
        number += 1
    return candidate


def unique_box_sku():
    from uuid import uuid4

    while True:
        sku = f"BE-B-{uuid4().hex[:10].upper()}"
        if not Box.objects.filter(sku=sku).exists():
            return sku


def unique_collection_slug(base, instance):
    slug = base or "collection"
    candidate = slug
    number = 2
    taken = Collection.objects.all()
    if getattr(instance, "pk", None):
        taken = taken.exclude(pk=instance.pk)
    while taken.filter(slug=candidate).exists():
        suffix = f"-{number}"
        candidate = f"{slug[:200 - len(suffix)]}{suffix}"
        number += 1
    return candidate


class CollectionBoxPicker(forms.CheckboxSelectMultiple):
    template_name = "admin/brandat_egy/collection_box_picker.html"

    def __init__(self, attrs=None):
        super().__init__(attrs)
        self.queryset = Box.objects.none()

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        selected = {str(item) for item in context["widget"]["value"]}
        rows = []
        for box in self.queryset:
            rows.append(
                {
                    "id": box.pk,
                    "name_ar": box.name_ar,
                    "name_en": box.name_en,
                    "sku": box.sku,
                    "is_active": box.is_active,
                    "selected": str(box.pk) in selected,
                    "search": " ".join(
                        part
                        for part in (box.name_ar, box.name_en, box.sku)
                        if part
                    ).lower(),
                }
            )
        rows.sort(key=lambda row: (not row["selected"], row["name_ar"]))
        context["picker_boxes"] = rows
        context["picker_selected"] = sum(row["selected"] for row in rows)
        return context

    def render(self, name, value, attrs=None, renderer=None):
        context = self.get_context(name, value, attrs)
        return mark_safe(get_template(self.template_name).render(context))


class CollectionAdminForm(forms.ModelForm):
    boxes = forms.ModelMultipleChoiceField(
        queryset=Box.objects.none(),
        required=False,
        widget=CollectionBoxPicker(),
        label=_("Boxes"),
        help_text=_("Press a box to add it to this collection or take it out."),
    )

    class Meta:
        model = Collection
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        boxes = Box.objects.filter(is_active=True).order_by("name_ar", "pk")
        self.fields["boxes"].queryset = boxes
        self.fields["boxes"].widget.queryset = boxes

    def clean(self):
        cleaned = super().clean()
        boxes = cleaned.get("boxes")
        has_box_for_sale = (
            boxes is not None and boxes.filter(is_active=True).exists()
        )
        if cleaned.get("is_active") and not has_box_for_sale:
            self.add_error(
                "is_active",
                _("A shown collection needs at least one box that is for sale."),
            )
        return cleaned

    def save(self, commit=True):
        collection = super().save(commit=False)
        if not collection.slug:
            base = arabic_to_slug(collection.name_ar) or slugify(collection.name_en or "")
            collection.slug = unique_collection_slug(base, collection)
        if commit:
            collection.save()
            self.save_m2m()
        return collection


@admin.register(Collection)
class CollectionAdmin(StoreAdmin):
    form = CollectionAdminForm
    list_display = ("name_ar", "name_en", "slug", "boxes_on_store", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name_ar", "name_en", "slug")

    fieldsets = (
        (
            _("Collection names"),
            {
                "fields": (
                    ("name_ar", "name_en"),
                    ("description_ar", "description_en"),
                    "is_active",
                    "boxes",
                ),
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            store_boxes=Count(
                "boxes",
                filter=Q(boxes__is_active=True),
                distinct=True,
            )
        )

    def get_changeform_initial_data(self, request):
        return {"is_active": False}

    @admin.display(description=_("Boxes on the store"), ordering="store_boxes")
    def boxes_on_store(self, obj):
        return obj.store_boxes


def offer_variant_label(variant):
    size = f" — {variant.size}" if variant.size else ""
    return (
        f"{variant.product.name_ar}{size} — "
        f"{variant.price} {gettext('EGP')}"
    )


def offer_box_label(box):
    return f"{box.name_ar} — {box.price} {gettext('EGP')}"


class OfferChangeList(ChangeList):
    def get_filters_params(self, params=None):
        lookup_params = super().get_filters_params(params)
        for key in ("deal", "category", "start", "export"):
            lookup_params.pop(key, None)
        return lookup_params


class DailyOfferAdminForm(forms.ModelForm):
    class Meta:
        model = DailyOffer
        fields = "__all__"

    def validate_constraints(self):
        try:
            self.instance.validate_constraints(
                exclude=self._get_validation_exclusions()
            )
        except ValidationError as exc:
            kept = _without_offer_constraint_names(exc)
            if kept is not None:
                self._update_errors(kept)


def _without_offer_constraint_names(exc):
    hidden = ("daily_offer_exactly_one_target", "daily_offer_end_after_start")
    if not hasattr(exc, "error_dict"):
        text = " ".join(exc.messages)
        if any(name in text for name in hidden):
            return None
        return exc
    kept = {}
    for field, errors in exc.error_dict.items():
        visible = [
            error
            for error in errors
            if not any(name in " ".join(error.messages) for name in hidden)
        ]
        if visible:
            kept[field] = visible
    if not kept:
        return None
    return ValidationError(kept)


@admin.register(DailyOffer)
class DailyOfferAdmin(StoreAdmin):
    form = DailyOfferAdminForm
    change_list_template = "admin/brandat_egy/offer_changelist.html"
    list_fullwidth = True
    list_per_page = 8
    ordering = ("-starts_at", "-pk")
    list_display = (
        "id",
        "variant",
        "box",
        "price",
        "starts_at",
        "ends_at",
        "is_active",
    )
    fieldsets = (
        (
            _("What is on offer"),
            {
                "description": _(
                    "Choose either a product option or a box, not both."
                ),
                "fields": (
                    ("variant", "box"),
                    ("price", "is_active"),
                ),
            },
        ),
        (
            _("Offer period"),
            {"fields": (("starts_at", "ends_at"),)},
        ),
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

    def get_changelist(self, request, **kwargs):
        return OfferChangeList

    def get_queryset(self, request):
        qs = (
            super()
            .get_queryset(request)
            .select_related("variant__product", "box")
            .prefetch_related("variant__product__images", "box__images")
        )
        now = timezone.now()
        deal = request.GET.get("deal")
        if deal == "running":
            qs = qs.filter(is_active=True, starts_at__lte=now, ends_at__gt=now)
        elif deal == "scheduled":
            qs = qs.filter(is_active=True, starts_at__gt=now)
        elif deal == "ended":
            qs = qs.filter(ends_at__lte=now)
        elif deal == "stopped":
            qs = qs.filter(is_active=False)
        category = request.GET.get("category")
        if category and str(category).isdigit():
            qs = qs.filter(
                Q(variant__product__category_id=category)
                | Q(box__items__variant__product__category_id=category)
            ).distinct()
        start = self._offer_day(request.GET.get("start"))
        if start is not None:
            qs = qs.filter(ends_at__date__gte=start)
        return qs

    def changelist_view(self, request, extra_context=None):
        if request.GET.get("export"):
            return self.export_offers(request)
        extra_context = extra_context or {}
        now = timezone.now()
        offers = DailyOffer.objects.all()
        extra_context["offer_stats"] = {
            "total": offers.count(),
            "running": offers.filter(
                is_active=True,
                starts_at__lte=now,
                ends_at__gt=now,
            ).count(),
            "scheduled": offers.filter(is_active=True, starts_at__gt=now).count(),
            "ended": offers.filter(ends_at__lte=now).count(),
        }
        extra_context["offer_categories"] = Category.objects.order_by("name_ar")
        return super().changelist_view(request, extra_context)

    def export_offers(self, request):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="daily-offers.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(["المنتج", "السعر الأصلي", "سعر العرض", "البداية", "النهاية", "الحالة"])
        for offer in self.get_queryset(request):
            target = offer.variant or offer.box
            regular = getattr(target, "price", "")
            name = str(target) if target is not None else ""
            writer.writerow([
                name,
                regular,
                offer.price,
                offer.starts_at.isoformat() if offer.starts_at else "",
                offer.ends_at.isoformat() if offer.ends_at else "",
                offer.offer_status(),
            ])
        return response

    @staticmethod
    def _offer_day(value):
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "variant":
            kwargs["queryset"] = ProductVariant.objects.select_related(
                "product"
            ).order_by("product__name_ar", "size", "pk")
        elif db_field.name == "box":
            kwargs["queryset"] = Box.objects.order_by("name_ar", "pk")
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if formfield is None:
            return formfield
        if db_field.name == "variant":
            formfield.label_from_instance = offer_variant_label
        elif db_field.name == "box":
            formfield.label_from_instance = offer_box_label
        return formfield


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


HIDDEN_ADMIN_MODELS = (
    OutstandingToken,
    BlacklistedToken,
    Favorite,
)

for model in HIDDEN_ADMIN_MODELS:
    if admin.site.is_registered(model):
        admin.site.unregister(model)


def _money_line():
    return ExpressionWrapper(
        F("price") * F("stock"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )


def _page(queryset, request, per_page):
    paginator = Paginator(queryset, per_page)
    raw = request.GET.get("p") or 1
    try:
        return paginator.page(raw)
    except Exception:
        return paginator.page(1)


def shipping_view(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    formset_class = forms.modelformset_factory(
        ShippingRate,
        fields=("name_ar", "fee", "is_active"),
        extra=0,
    )
    queryset = ShippingRate.objects.order_by("name_ar")
    if request.method == "POST":
        formset = formset_class(request.POST, queryset=queryset)
        if formset.is_valid():
            formset.save()
            messages.success(request, "اتحفظت مصاريف الشحن.")
            return redirect("admin:brandat_shipping")
    else:
        formset = formset_class(queryset=queryset)
    context = {
        **admin.site.each_context(request),
        "title": "مصاريف الشحن",
        "formset": formset,
    }
    return render(request, "admin/brandat_egy/shipping.html", context)


def inventory_view(request):
    qs = (
        ProductVariant.objects
        .select_related("product", "product__category")
        .prefetch_related("product__images")
        .order_by("product__name_ar", "sku")
    )
    query = request.GET.get("q", "").strip()
    if query:
        qs = qs.filter(
            Q(sku__icontains=query)
            | Q(product__name_ar__icontains=query)
            | Q(product__name_en__icontains=query)
            | Q(size__icontains=query)
        )
    stock_tab = request.GET.get("stock") or "all"
    if stock_tab == "low":
        qs = qs.filter(stock__gt=0, stock__lte=LOW_STOCK_THRESHOLD)
    elif stock_tab == "out":
        qs = qs.filter(stock=0)
    else:
        stock_tab = "all"
    category_id = request.GET.get("category", "")
    if str(category_id).isdigit():
        qs = qs.filter(product__category_id=int(category_id))
    else:
        category_id = ""

    if request.GET.get("export"):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="inventory.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(["المنتج", "الحجم", "الكود", "الكمية", "السعر"])
        for variant in qs:
            writer.writerow([
                variant.product.name_ar,
                variant.size,
                variant.sku,
                variant.stock,
                variant.price,
            ])
        return response

    variants = ProductVariant.objects.all()
    value = variants.aggregate(total=Sum(_money_line()))["total"] or Decimal("0")
    context = {
        **admin.site.each_context(request),
        "title": "المخزون",
        "page": _page(qs, request, 10),
        "query": query,
        "stock_tab": stock_tab,
        "category_id": category_id,
        "categories": Category.objects.order_by("name_ar"),
        "low_stock": LOW_STOCK_THRESHOLD,
        "stats": {
            "total": variants.count(),
            "low": variants.filter(stock__gt=0, stock__lte=LOW_STOCK_THRESHOLD).count(),
            "out": variants.filter(stock=0).count(),
            "value": value,
        },
    }
    return render(request, "admin/brandat_egy/inventory.html", context)


def reports_view(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    if request.GET.get("period") or request.GET.get("start"):
        start, end, key = _dashboard_range(request)
    else:
        today = timezone.localdate()
        start, end, key = today, today, "today"
    orders = Order.objects.filter(
        created_at__date__gte=start,
        created_at__date__lte=end,
    )
    delivered = orders.filter(status="delivered")
    delivered_count = delivered.count()
    revenue = _revenue_between(start, end)
    shipping = delivered.aggregate(total=Sum("shipping_fee"))["total"] or Decimal("0")
    status_labels = (
        ("pending", "بانتظار الدفع"),
        ("confirmed", "تم تأكيد الطلب"),
        ("preparing", "جاري التجهيز"),
        ("shipped", "تم الشحن"),
        ("delivered", "تم التسليم"),
        ("cancelled", "ملغى"),
    )
    status_rows = [
        {"label": label, "count": orders.filter(status=code).count()}
        for code, label in status_labels
    ]
    box_rows = list(
        OrderBox.objects.filter(
            order__status="delivered",
            order__created_at__date__gte=start,
            order__created_at__date__lte=end,
        )
        .values("name_ar")
        .annotate(
            sold=Sum("quantity"),
            revenue=Sum(
                F("price") * F("quantity"),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            ),
        )
        .order_by("-revenue")[:8]
    )
    days = []
    cursor = start
    shown_days = 0
    while cursor <= end and shown_days < 62:
        day_orders = orders.filter(created_at__date=cursor)
        day_delivered = day_orders.filter(status="delivered")
        days.append({
            "label": date_format(cursor, "j F Y"),
            "orders": day_orders.count(),
            "delivered": day_delivered.count(),
            "revenue": _revenue_between(cursor, cursor),
        })
        cursor += timedelta(days=1)
        shown_days += 1
    variants = ProductVariant.objects.select_related("product")
    low_variants = list(
        variants.filter(stock__gt=0, stock__lte=LOW_STOCK_THRESHOLD)
        .order_by("stock", "product__name_ar")[:8]
    )
    out_variants = list(
        variants.filter(stock=0).order_by("product__name_ar")[:8]
    )
    stock_value = variants.aggregate(total=Sum(_money_line()))["total"] or Decimal("0")
    User = get_user_model()
    new_customers = User.objects.filter(
        is_staff=False,
        is_superuser=False,
        date_joined__date__gte=start,
        date_joined__date__lte=end,
    ).count()
    context = {
        **admin.site.each_context(request),
        "title": "التقارير",
        "range_label": _range_label(start, end, key),
        "range_key": key,
        "range_start": start,
        "range_end": end,
        "range_clipped": (end - start).days > 61,
        "orders_count": orders.count(),
        "delivered_count": delivered_count,
        "revenue": revenue,
        "shipping": shipping,
        "average_order": revenue / delivered_count if delivered_count else Decimal("0"),
        "status_rows": status_rows,
        "days": days,
        "top_products": get_top_products(limit=8, start_date=start, end_date=end),
        "top_boxes": box_rows,
        "new_customers": new_customers,
        "reviews_count": Review.objects.filter(
            created_at__date__gte=start,
            created_at__date__lte=end,
        ).count(),
        "inventory": {
            "total": variants.count(),
            "low": variants.filter(stock__gt=0, stock__lte=LOW_STOCK_THRESHOLD).count(),
            "out": variants.filter(stock=0).count(),
            "value": stock_value,
            "low_rows": low_variants,
            "out_rows": out_variants,
        },
    }
    return render(request, "admin/brandat_egy/reports.html", context)


def activity_view(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    entries = LogEntry.objects.select_related("user", "content_type")
    query = request.GET.get("q", "").strip()
    if query:
        entries = entries.filter(
            Q(object_repr__icontains=query) | Q(change_message__icontains=query)
        )
    module = request.GET.get("module", "")
    if str(module).isdigit():
        entries = entries.filter(content_type_id=int(module))
    person = request.GET.get("user", "")
    if str(person).isdigit():
        entries = entries.filter(user_id=int(person))
    action = request.GET.get("action", "")
    if action in {"1", "2", "3"}:
        entries = entries.filter(action_flag=int(action))

    page = _page(entries, request, 10)
    rows = []
    pills = {1: "studio-pill", 2: "studio-pill--blue", 3: "studio-pill--red"}
    actions = {1: "إضافة", 2: "تعديل", 3: "حذف"}
    for entry in page.object_list:
        model = entry.content_type.model_class()
        user = entry.user
        message = entry.get_change_message()
        detail = entry.object_repr
        if message and message not in detail:
            detail = f"{detail} — {message}"
        rows.append({
            "entry": entry,
            "module": model._meta.verbose_name if model else entry.content_type.model,
            "user_name": (user.customer_name or user.phone) if user else "مستخدم محذوف",
            "role": "مدير المتجر" if user and user.is_superuser else "موظف",
            "action": actions.get(entry.action_flag, "تعديل"),
            "pill": pills.get(entry.action_flag, "studio-pill"),
            "detail": detail,
        })
    page.object_list = rows
    modules = []
    for content_type in ContentType.objects.filter(logentry__isnull=False).distinct():
        model = content_type.model_class()
        modules.append({
            "id": content_type.pk,
            "name": model._meta.verbose_name if model else content_type.model,
        })
    context = {
        **admin.site.each_context(request),
        "title": "سجل النشاط",
        "page": page,
        "query": query,
        "modules": modules,
        "people": get_user_model().objects.filter(logentry__isnull=False).distinct().order_by("customer_name"),
    }
    return render(request, "admin/brandat_egy/activity.html", context)


def _store_page(request, title, intro):
    if not request.user.is_superuser:
        raise PermissionDenied
    from django.shortcuts import render

    context = {
        **admin.site.each_context(request),
        "title": title,
        "intro": intro,
    }
    return render(request, "admin/brandat_egy/simple_page.html", context)


_original_admin_urls = admin.site.get_urls


def _admin_urls():
    return [
        path(
            "shipping/",
            admin.site.admin_view(shipping_view),
            name="brandat_shipping",
        ),
        path(
            "inventory/",
            admin.site.admin_view(inventory_view),
            name="brandat_inventory",
        ),
        path(
            "reports/",
            admin.site.admin_view(reports_view),
            name="brandat_reports",
        ),
        path(
            "activity/",
            admin.site.admin_view(activity_view),
            name="brandat_activity",
        ),
        path(
            "coupons/",
            admin.site.admin_view(
                lambda request: _store_page(
                    request,
                    gettext("Coupons"),
                    gettext("Coupon codes are not set up on the store yet."),
                )
            ),
            name="brandat_coupons",
        ),
    ] + _original_admin_urls()


admin.site.get_urls = _admin_urls


