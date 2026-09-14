"""DRF serializer for reviews."""

from rest_framework import serializers

from reviews.models import Review


class ReviewSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    restaurant_name = serializers.CharField(source="restaurant.name", read_only=True)
    order_number = serializers.CharField(source="order.order_number", read_only=True)

    class Meta:
        model = Review
        fields = [
            "id", "customer", "customer_name", "restaurant", "restaurant_name", "order",
            "order_number", "rating", "comment", "reply", "is_hidden", "created_at",
        ]
        read_only_fields = ["customer", "restaurant", "is_hidden", "created_at"]

    def validate(self, attrs):
        order = attrs.get("order") or getattr(self.instance, "order", None)
        request = self.context.get("request")
        if order is None:
            raise serializers.ValidationError({"order": "A delivered order is required to review."})
        if request and order.customer_id != request.user.pk:
            raise serializers.ValidationError({"order": "You can only review your own orders."})
        if order.order_status != "DELIVERED":
            raise serializers.ValidationError({"order": "You can review only after the order is delivered."})
        if not self.instance and hasattr(order, "review"):
            raise serializers.ValidationError({"order": "This order already has a review."})
        return attrs
