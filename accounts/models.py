from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import CustomUserManager


class User(AbstractUser):
    username = None

    customer_name = models.CharField(
        max_length=150,
    )

    phone = models.CharField(
        max_length=20,
        unique=True,
    )

    email = models.EmailField(
        blank=True,
    )

    address = models.TextField(
        blank=True,
    )

    USERNAME_FIELD = "phone"

    REQUIRED_FIELDS = [
        "customer_name",
    ]

    objects = CustomUserManager()

    def __str__(self):
        return f"{self.customer_name} - {self.phone}"