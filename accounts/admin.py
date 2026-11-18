from django import forms
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.db.models import Max
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import path
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from .models import User
from .staff import store_staff_group

# Register your models here.
class CustomerCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("phone", "customer_name")


class StoreStaffForm(forms.Form):
    customer_name = forms.CharField(
        label="الاسم",
        max_length=150,
        widget=forms.TextInput(attrs={"data-testid": "staff-name"}),
    )
    phone = forms.CharField(
        label="الهاتف",
        max_length=20,
        widget=forms.TextInput(attrs={"data-testid": "staff-phone", "dir": "ltr"}),
    )
    password1 = forms.CharField(
        label="كلمة المرور",
        required=False,
        widget=forms.PasswordInput(attrs={"data-testid": "staff-password"}),
    )
    password2 = forms.CharField(
        label="تأكيد كلمة المرور",
        required=False,
        widget=forms.PasswordInput(attrs={"data-testid": "staff-password-confirm"}),
    )
    is_active = forms.BooleanField(
        label="يقدر يسجّل الدخول",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"data-testid": "staff-active"}),
    )

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        if instance is not None and instance.is_superuser:
            self.fields.pop("is_active", None)
        if instance is not None:
            self.fields["password1"].label = "كلمة مرور جديدة"
            self.fields["password2"].label = "تأكيد كلمة المرور الجديدة"

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        taken = User.objects.filter(phone=phone)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise forms.ValidationError("الرقم مستخدم لحساب آخر.")
        return phone

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password1") or ""
        confirm = cleaned.get("password2") or ""
        if self.instance is None and not password:
            self.add_error("password1", "اكتب كلمة المرور.")
        if password or confirm:
            if password != confirm:
                self.add_error("password2", "كلمتا المرور غير متطابقتين.")
            else:
                try:
                    validate_password(password, self.instance)
                except ValidationError as error:
                    self.add_error("password1", error)
        if (
            "is_active" in self.fields
            and self.instance is not None
            and self.instance.is_superuser
            and not cleaned.get("is_active")
        ):
            self.add_error("is_active", "متوقفش حساب المدير من هنا.")
        return cleaned

@admin.register(User)
class CustomerAdmin(UserAdmin):
    add_form = CustomerCreationForm

    ordering = ("customer_name",)
    list_display = (
        "phone",
        "customer_name",
        "email",
        "order_count",
        "last_order",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("phone", "customer_name", "email")

    def get_urls(self):
        return [
            path(
                "employees/",
                self.admin_site.admin_view(self.employees_view),
                name="accounts_staff",
            ),
            path(
                "employees/add/",
                self.admin_site.admin_view(self.employee_add_view),
                name="accounts_staff_add",
            ),
            path(
                "employees/<int:user_id>/",
                self.admin_site.admin_view(self.employee_change_view),
                name="accounts_staff_change",
            ),
        ] + super().get_urls()

    def _require_manager(self, request):
        if not request.user.is_superuser:
            raise PermissionDenied

    def employees_view(self, request):
        self._require_manager(request)
        staff = User.objects.filter(is_staff=True).order_by("customer_name", "phone")
        context = {
            **self.admin_site.each_context(request),
            "title": "الموظفون",
            "staff": staff,
        }
        return render(request, "admin/accounts/employees.html", context)

    def employee_add_view(self, request):
        self._require_manager(request)
        form = StoreStaffForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            user = User.objects.create_user(
                phone=form.cleaned_data["phone"],
                password=form.cleaned_data["password1"],
                customer_name=form.cleaned_data["customer_name"],
                is_staff=True,
                is_active=form.cleaned_data["is_active"],
            )
            user.groups.add(store_staff_group())
            messages.success(request, "تمت إضافة الموظف. يسجّل الدخول برقم الهاتف وكلمة المرور.")
            return redirect("admin:accounts_staff")
        return self._employee_form(request, form, title="أضف موظف")

    def employee_change_view(self, request, user_id):
        self._require_manager(request)
        user = User.objects.filter(pk=user_id, is_staff=True).first()
        if user is None:
            return redirect("admin:accounts_staff")
        form = StoreStaffForm(
            request.POST or None,
            instance=user,
            initial={
                "customer_name": user.customer_name,
                "phone": user.phone,
                "is_active": user.is_active,
            },
        )
        if request.method == "POST" and form.is_valid():
            user.customer_name = form.cleaned_data["customer_name"]
            user.phone = form.cleaned_data["phone"]
            if not user.is_superuser:
                user.is_active = form.cleaned_data["is_active"]
            if form.cleaned_data["password1"]:
                user.set_password(form.cleaned_data["password1"])
            user.save()
            if not user.is_superuser:
                user.groups.add(store_staff_group())
            messages.success(request, "تم حفظ بيانات الموظف.")
            return redirect("admin:accounts_staff")
        return self._employee_form(request, form, title="تعديل الموظف", employee=user)

    def _employee_form(self, request, form, title, employee=None):
        context = {
            **self.admin_site.each_context(request),
            "title": title,
            "form": form,
            "employee": employee,
        }
        return render(request, "admin/accounts/employee_form.html", context)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .filter(is_staff=False, is_superuser=False)
            .annotate(
                order_count=Count("orders", distinct=True),
                last_order_at=Max("orders__created_at"),
            )
        )

    @admin.display(description=_("Order count"), ordering="order_count")
    def order_count(self, obj):
        return obj.order_count

    @admin.display(description=_("Last order"), ordering="last_order_at")
    def last_order(self, obj):
        if not obj.last_order_at:
            return gettext("No orders yet.")
        return date_format(
            timezone.localtime(obj.last_order_at),
            "SHORT_DATETIME_FORMAT",
        )

    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        (_("Customer"), {"fields": ("customer_name", "email", "address")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            _("Dates"),
            {"fields": (("joined_on", "signed_in_at"),)},
        ),
    )

    customer_fieldsets = (
        (None, {"fields": ("phone",)}),
        (
            _("Customer"),
            {
                "description": _(
                    "This account was created by a customer. Permissions stay hidden so staff cannot grant access by mistake."
                ),
                "fields": (
                    "customer_name",
                    "email",
                    "address",
                    "is_active",
                ),
            },
        ),
        (
            _("Dates"),
            {"fields": (("joined_on", "signed_in_at"),)},
        ),
    )

    readonly_fields = ("joined_on", "signed_in_at")

    def get_fieldsets(self, request, obj=None):
        if not obj:
            return self.add_fieldsets
        if obj.is_staff or obj.is_superuser:
            return super().get_fieldsets(request, obj)
        return self.customer_fieldsets

    def has_change_permission(self, request, obj=None):
        if obj is not None and not obj.is_staff and not obj.is_superuser:
            return False
        return super().has_change_permission(request, obj)

    @admin.display(description=_("Joined on"))
    def joined_on(self, obj):
        if not obj.date_joined:
            return "—"
        return date_format(
            timezone.localtime(obj.date_joined),
            "DATETIME_FORMAT",
        )

    @admin.display(description=_("Last sign in"))
    def signed_in_at(self, obj):
        if not obj.last_login:
            return gettext("Has not signed in yet")
        return date_format(
            timezone.localtime(obj.last_login),
            "DATETIME_FORMAT",
        )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("phone", "customer_name", "password1", "password2"),
            },
        ),
    )
