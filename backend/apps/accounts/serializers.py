from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Traveller, User


class UserSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "public_id", "email", "first_name", "last_name",
            "phone", "locale", "mfa_enabled", "roles",
        ]
        read_only_fields = ["public_id", "email", "mfa_enabled", "roles"]

    def get_roles(self, obj: User) -> list[str]:
        return sorted(obj.role_codes)


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=10)
    first_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)

    def validate_email(self, value: str) -> str:
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value

    def create(self, validated_data: dict) -> User:
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)


class TravellerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Traveller
        fields = [
            "public_id", "first_name", "last_name", "dob", "gender", "nationality",
            "doc_type", "doc_number", "doc_expiry", "doc_issuing_country",
            "frequent_flyer_number", "is_primary",
        ]
        read_only_fields = ["public_id"]
        extra_kwargs = {"doc_number": {"write_only": True}}
