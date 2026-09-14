"""DRF serializer for coupons."""

from rest_framework import serializers

from offers.models import Coupon


class CouponSerializer(serializers.ModelSerializer):
    display_value = serializers.CharField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = Coupon
        fields = [
            "id", "code", "title", "description", "discount_type", "discount_value",
            "minimum_order", "maximum_discount", "valid_from", "valid_until",
            "usage_limit", "used_count", "per_user_limit", "restaurant",
            "first_order_only", "is_active", "display_value", "is_expired",
        ]
        read_only_fields = ["used_count"]
