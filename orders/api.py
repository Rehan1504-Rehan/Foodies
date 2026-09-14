"""Order + notification API (/api/orders/, /api/notifications/)."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from orders.models import Notification, Order, OrderStatus
from orders.serializers import (
    NotificationSerializer,
    OrderSerializer,
    OrderStatusUpdateSerializer,
    PlaceOrderSerializer,
)
from orders.services import cancel_order, create_order_from_cart


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    """Orders are always scoped to the requesting account."""

    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "order_number"

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.role == "ADMIN":
            queryset = Order.objects.all()
        elif user.role == "RESTAURANT_OWNER":
            queryset = Order.objects.filter(restaurant__owner=user)
        elif user.role == "DELIVERY_BOY":
            queryset = Order.objects.filter(delivery_boy=user)
        else:
            queryset = Order.objects.filter(customer=user)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(order_status=status_filter)
        return queryset.select_related("restaurant", "customer", "delivery_boy").prefetch_related("items")

    @action(detail=False, methods=["post"])
    def checkout(self, request):
        """Create a real order from the customer's database cart."""
        serializer = PlaceOrderSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        address = request.user.addresses.get(pk=data["address_id"])
        try:
            order = create_order_from_cart(
                user=request.user,
                address=address,
                coupon_code=data.get("coupon_code", ""),
                payment_method=data.get("payment_method", "COD"),
                special_instructions=data.get("special_instructions", ""),
            )
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def track(self, request, order_number=None):
        order = self.get_object()
        return Response(
            {
                "order_number": order.order_number,
                "status": order.order_status,
                "status_label": order.status_label,
                "progress": order.progress_percent,
                "delivery_boy": order.delivery_partner_name,
                "steps": [
                    {"label": label, "state": state, "at": history.created_at if history else None}
                    for label, state, history in order.tracking_steps
                ],
            }
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, order_number=None):
        order = self.get_object()
        if order.customer_id != request.user.pk and not request.user.is_superuser:
            return Response({"detail": "You can only cancel your own orders."}, status=status.HTTP_403_FORBIDDEN)
        try:
            cancel_order(order, actor=request.user, reason=request.data.get("reason") or "Cancelled by customer")
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, order_number=None):
        """Restaurant owners, delivery partners and admins move orders forward."""
        order = self.get_object()
        user = request.user
        serializer = OrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]

        allowed = False
        if user.is_superuser or user.role == "ADMIN":
            allowed = True
        elif user.role == "RESTAURANT_OWNER" and order.restaurant.owner_id == user.pk:
            allowed = new_status in {OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY_FOR_PICKUP, OrderStatus.CANCELLED}
        elif user.role == "DELIVERY_BOY" and order.delivery_boy_id == user.pk:
            allowed = new_status in {OrderStatus.PICKED_UP, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED}
        if not allowed:
            return Response({"detail": "You cannot update this order."}, status=status.HTTP_403_FORBIDDEN)
        if not order.can_transition_to(new_status):
            return Response(
                {"detail": f"Cannot move from {order.status_label} to {dict(OrderStatus.choices)[new_status]}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.set_status(new_status, note=serializer.validated_data.get("note", "Updated via API"), actor=user)
        return Response(OrderSerializer(order).data)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        updated = Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({"updated": updated, "message": "All notifications marked as read."})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def unread_count(request):
    return Response({"unread": Notification.objects.filter(recipient=request.user, is_read=False).count()})
