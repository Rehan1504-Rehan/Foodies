"""DRF serializers for accounts and addresses."""

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from accounts.models import Address

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    role_label = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "full_name", "phone", "role",
            "role_label", "profile_image", "is_active", "date_joined",
        ]
        read_only_fields = ["id", "role", "is_active", "date_joined"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password], style={"input_type": "password"})
    password_confirm = serializers.CharField(write_only=True, style={"input_type": "password"})
    role = serializers.ChoiceField(choices=["CUSTOMER", "RESTAURANT_OWNER", "DELIVERY_BOY"], default="CUSTOMER")

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "phone", "role", "password", "password_confirm"]

    def validate_email(self, value):
        value = value.lower().strip()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        role = validated_data.pop("role", "CUSTOMER")
        user = User(**validated_data, role=role)
        user.set_password(password)
        user.save()
        if role == "DELIVERY_BOY":
            from delivery.models import DeliveryBoyProfile

            DeliveryBoyProfile.objects.get_or_create(user=user)
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(username=attrs["email"].lower().strip(), password=attrs["password"])
        if user is None:
            raise serializers.ValidationError("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError("This account has been blocked. Contact FOODIES support.")
        attrs["user"] = user
        return attrs


class AddressSerializer(serializers.ModelSerializer):
    full_address = serializers.CharField(read_only=True)

    class Meta:
        model = Address
        fields = [
            "id", "label", "full_name", "phone", "address_line", "area", "city", "state",
            "pincode", "landmark", "address_type", "latitude", "longitude", "is_default",
            "full_address", "created_at",
        ]
        read_only_fields = ["id", "created_at"]
