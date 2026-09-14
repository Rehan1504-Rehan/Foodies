"""DRF serializers for orders, order items and notifications."""

from rest_framework import serializers

from orders.models import Notification, Order, OrderItem, OrderStatus, OrderStatusHistory


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ["id", "food_item", "food_name", "category_name", "is_veg", "price", "mrp", "quantity", "total"]


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = OrderStatusHistory
        fields = ["id", "status", "label", "note", "created_at"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    restaurant_name = serializers.CharField(source="restaurant.name", read_only=True)
    restaurant_slug = serializers.CharField(source="restaurant.slug", read_only=True)
    status_label = serializers.CharField(read_only=True)
    delivery_boy_name = serializers.CharField(source="delivery_partner_name", read_only=True)
    progress_percent = serializers.IntegerField(read_only=True)
    is_cancellable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "restaurant", "restaurant_name", "restaurant_slug",
            "delivery_boy", "delivery_boy_name", "customer_name", "customer_phone",
            "delivery_address_text", "subtotal", "discount", "delivery_fee", "tax",
            "platform_fee", "coupon_discount", "total_amount", "payment_status",
            "order_status", "status_label", "progress_percent", "is_cancellable",
            "special_instructions", "estimated_delivery_time", "items",
            "created_at", "updated_at", "delivered_at",
        ]
        read_only_fields = [
            "order_number", "subtotal", "discount", "delivery_fee", "tax", "platform_fee",
            "coupon_discount", "total_amount", "payment_status", "order_status", "delivery_boy",
        ]


class PlaceOrderSerializer(serializers.Serializer):
    """Checkout payload — only ids and a coupon code are accepted.

    Amounts are never read from the request: the server reprices the cart.
    """

    address_id = serializers.IntegerField()
    coupon_code = serializers.CharField(required=False, allow_blank=True)
    payment_method = serializers.ChoiceField(choices=["COD", "RAZORPAY", "MOCK", "UPI"], default="COD")
    special_instructions = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate_address_id(self, value):
        user = self.context["request"].user
        if not user.addresses.filter(pk=value).exists():
            raise serializers.ValidationError("That delivery address does not belong to your account.")
        return value


class OrderStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=OrderStatus.choices)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "title", "message", "kind", "url", "order", "is_read", "created_at"]
