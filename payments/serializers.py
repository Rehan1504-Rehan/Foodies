"""DRF serializer for payments."""

from rest_framework import serializers

from payments.models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    restaurant_name = serializers.CharField(source="order.restaurant.name", read_only=True)
    method_label = serializers.CharField(source="get_payment_method_display", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id", "payment_id", "order", "order_number", "restaurant_name", "amount",
            "payment_method", "method_label", "status", "created_at",
        ]
        read_only_fields = fields
