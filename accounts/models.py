from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.db import models

from .managers import CustomUserManager


class User(AbstractUser):
    username = None

    customer_name = models.CharField(
        _("Account name"),
        max_length=150,
    )

    phone = models.CharField(
        _("Phone"),
        max_length=20,
        unique=True,
    )

    email = models.EmailField(
        _("Email"),
        blank=True,
    )

    address = models.TextField(
        _("Customer address"),
        blank=True,
    )

    USERNAME_FIELD = "phone"

    REQUIRED_FIELDS = [
        "customer_name",
    ]

    objects = CustomUserManager()

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")

    def __str__(self):
        return f"{self.customer_name} - {self.phone}"