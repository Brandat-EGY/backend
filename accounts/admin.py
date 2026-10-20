from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserCreationForm

from .models import User

# Register your models here.
class CustomerCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("phone", "customer_name")

@admin.register(User)
class CustomerAdmin(UserAdmin):
    add_form = CustomerCreationForm

    ordering = ("customer_name",)
    list_display = ("phone", "customer_name", "email", "is_staff", "is_active")
    search_fields = ("phone", "customer_name", "email")

    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Customer", {"fields": ("customer_name", "email", "address")}),
        (
            "Permissions",
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
        ("Dates", {"fields": ("last_login", "date_joined")}),
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
