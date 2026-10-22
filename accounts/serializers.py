
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from rest_framework import serializers


User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )

    password_confirm = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )

    class Meta:
        model = User
        fields = (
            "customer_name",
            "phone",
            "email",
            "address",
            "password",
            "password_confirm",
        )

    def validate(self, attrs):
        password = attrs["password"]
        password_confirm = attrs["password_confirm"]

        if password != password_confirm:
            raise serializers.ValidationError({
                "password_confirm": "Passwords do not match."
            })

        user = User(
            customer_name=attrs["customer_name"],
            phone=attrs["phone"],
            email=attrs.get("email", ""),
            address=attrs.get("address", ""),
        )

        try:
            validate_password(password, user=user)
        except ValidationError as error:
            raise serializers.ValidationError({
                "password": error.messages
            })

        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")

        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    password=password,
                    **validated_data,
                )
        except IntegrityError:
            if User.objects.filter(
                phone=validated_data["phone"]
            ).exists():
                raise serializers.ValidationError({
                    "phone": "This phone number is already registered."
                })
            raise

        return user


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)

    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )



class CustomerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User

        fields = (
            "id",
            "customer_name",
            "phone",
            "email",
            "address",
        )

        read_only_fields = (
            "id",
            "phone",
        )

    def validate(self, attrs):
        allowed_fields = {
            "customer_name",
            "email",
            "address",
        }

        unexpected = (
            set(self.initial_data) - allowed_fields
        )

        if unexpected:
            raise serializers.ValidationError({
                field: "This field cannot be updated."
                for field in sorted(unexpected)
            })

        return attrs
