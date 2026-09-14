"""DRF serializers for delivery partners, assignments and earnings."""

from rest_framework import serializers

from delivery.models import DeliveryAssignment, DeliveryBoyProfile, DeliveryEarning


class DeliveryProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    profile_image = serializers.ImageField(source="user.profile_image", read_only=True)
    active_orders = serializers.IntegerField(read_only=True)
    completed_count = serializers.IntegerField(read_only=True)
    today_earnings = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    total_earnings = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = DeliveryBoyProfile
        fields = [
            "id", "full_name", "email", "phone", "profile_image", "vehicle_type",
            "vehicle_number", "license_number", "current_area", "availability_status",
            "is_approved", "earning_per_delivery", "active_orders", "completed_count",
            "today_earnings", "total_earnings",
        ]
        read_only_fields = ["is_approved", "earning_per_delivery", "id"]


class DeliveryAssignmentSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    order_status = serializers.CharField(source="order.order_status", read_only=True)
    customer_name = serializers.CharField(source="order.customer_name", read_only=True)
    customer_phone = serializers.CharField(source="order.customer_phone", read_only=True)
    delivery_address = serializers.CharField(source="order.delivery_address_text", read_only=True)
    restaurant_name = serializers.CharField(source="order.restaurant.name", read_only=True)
    restaurant_address = serializers.CharField(source="order.restaurant.address", read_only=True)
    order_amount = serializers.DecimalField(source="order.total_amount", max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = DeliveryAssignment
        fields = [
            "id", "order", "order_number", "order_status", "customer_name", "customer_phone",
            "delivery_address", "restaurant_name", "restaurant_address", "order_amount",
            "status", "distance_km", "earning_amount", "assigned_at", "accepted_at",
            "picked_up_at", "out_for_delivery_at", "delivered_at",
        ]
        read_only_fields = fields


class DeliveryEarningSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    restaurant_name = serializers.CharField(source="order.restaurant.name", read_only=True)

    class Meta:
        model = DeliveryEarning
        fields = ["id", "order", "order_number", "restaurant_name", "amount", "status", "settled_at", "created_at"]
        read_only_fields = fields
