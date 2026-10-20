from django.shortcuts import render
from django.contrib.auth import authenticate
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated

from brandat_egy.favorites import Favorites
from .serializers import RegisterSerializer ,LoginSerializer



@method_decorator(ensure_csrf_cookie, name="dispatch")
class CSRFTokenAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            "message": "CSRF cookie set successfully."
        })


class RegisterAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.save()

        return Response(
            {
                "message": "Account created successfully.",
                "user": {
                    "id": user.pk,
                    "customer_name": user.customer_name,
                    "phone": user.phone,
                    "email": user.email,
                },
            },
            status=status.HTTP_201_CREATED,
        )



@method_decorator(csrf_protect, name="dispatch")
class LoginAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data["phone"]
        password = serializer.validated_data["password"]

        user = authenticate(
            request=request,
            phone=phone,
            password=password,
        )

        if user is None or not user.is_active:
            return Response(
                {"detail": "Invalid phone or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        Favorites(request).merge_guest_favorites(
            user=user
        )

        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "message": "Login successful.",
                "user": {
                    "id": user.pk,
                    "customer_name": user.customer_name,
                    "phone": user.phone,
                    "email": user.email,
                },
                "tokens": {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                },
            },
            status=status.HTTP_200_OK,
        )
    


class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        return Response({
            "id": user.pk,
            "customer_name": user.customer_name,
            "phone": user.phone,
            "email": user.email,
        })
