"""Delivery partner API (/api/delivery/...).

Every endpoint is restricted to the logged-in partner's own assignments.
"""

from django.db.models import Sum
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import HasRole, role_required
from delivery.models import DeliveryAssignment, DeliveryBoyProfile, DeliveryEarning
from delivery.serializers import (
    DeliveryAssignmentSerializer,
    DeliveryEarningSerializer,
    DeliveryProfileSerializer,
)
from orders.models import Order, OrderStatus
from orders.services import assign_delivery_boy, complete_delivery


class DeliveryProfileViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = DeliveryProfileSerializer
    permission_classes = [IsAuthenticated, HasRole]
    allowed_roles = ("DELIVERY_BOY", "ADMIN")

    def get_queryset(self):
        if self.request.user.role != "DELIVERY_BOY":
            return DeliveryBoyProfile.objects.none()
        return DeliveryBoyProfile.objects.filter(user=self.request.user).order_by("id")

    @action(detail=True, methods=["post"], url_path="availability")
    def availability(self, request, pk=None):
        profile = self.get_object()
        status_value = request.data.get("availability_status")
        if status_value not in dict(DeliveryBoyProfile.Availability.choices):
            return Response({"detail": "Invalid availability status."}, status=status.HTTP_400_BAD_REQUEST)
        if not profile.is_approved and status_value == "ONLINE":
            return Response({"detail": "Your account is pending approval."}, status=status.HTTP_403_FORBIDDEN)
        profile.set_availability(status_value)
        return Response({"availability_status": profile.availability_status, "message": f"You are now {status_value.lower()}."})


class DeliveryAssignmentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DeliveryAssignmentSerializer
    permission_classes = [IsAuthenticated, HasRole]
    allowed_roles = ("DELIVERY_BOY", "ADMIN")

    def get_queryset(self):
        user = self.request.user
        queryset = DeliveryAssignment.objects.select_related("order", "order__restaurant", "delivery_boy")
        if user.is_superuser or user.role == "ADMIN":
            pass
        elif user.role == "DELIVERY_BOY":
            queryset = queryset.filter(delivery_boy=user)
        else:
            return DeliveryAssignment.objects.none()
        state = self.request.query_params.get("status")
        if state:
            queryset = queryset.filter(status=state)
        return queryset.order_by("-assigned_at")

    def _mine(self, request):
        return DeliveryAssignment.objects.filter(delivery_boy=request.user).select_related("order").first()

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def available(self, request):
        """Ready-for-pickup orders that no partner has claimed yet."""
        if request.user.role != "DELIVERY_BOY":
            return Response({"detail": "Delivery partner account required."}, status=status.HTTP_403_FORBIDDEN)
        profile = DeliveryBoyProfile.objects.filter(user=request.user, is_approved=True).first()
        if profile is None:
            return Response({"detail": "Your account is not approved yet."}, status=status.HTTP_403_FORBIDDEN)
        orders = Order.objects.filter(
            order_status=OrderStatus.READY_FOR_PICKUP, delivery_boy__isnull=True
        ).select_related("restaurant")
        return Response(
            {
                "count": orders.count(),
                "orders": [
                    {
                        "order_number": order.order_number,
                        "restaurant": order.restaurant.name,
                        "restaurant_address": f"{order.restaurant.address}, {order.restaurant.area}",
                        "customer": order.customer_name,
                        "delivery_address": order.delivery_address_text,
                        "order_amount": order.total_amount,
                        "items": order.items_total_quantity,
                    }
                    for order in orders
                ],
            }
        )

    @action(detail=False, methods=["post"], url_path="claim")
    def claim(self, request):
        if request.user.role != "DELIVERY_BOY":
            return Response({"detail": "Delivery partner account required."}, status=status.HTTP_403_FORBIDDEN)
        order_number = request.data.get("order_number")
        order = Order.objects.filter(order_number=order_number, order_status=OrderStatus.READY_FOR_PICKUP, delivery_boy__isnull=True).first()
        if order is None:
            return Response({"detail": "That delivery is no longer available."}, status=status.HTTP_404_NOT_FOUND)
        try:
            assignment = assign_delivery_boy(order, request.user, actor=request.user)
        except Exception as exc:  # noqa: BLE001 - surfaced as a clean 400
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DeliveryAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        assignment = self.get_object()
        if assignment.delivery_boy_id != request.user.pk and not request.user.is_superuser:
            return Response({"detail": "This delivery is not assigned to you."}, status=status.HTTP_403_FORBIDDEN)
        new_status = request.data.get("status")
        mapping = {
            "ACCEPTED": OrderStatus.ASSIGNED,
            "PICKED_UP": OrderStatus.PICKED_UP,
            "OUT_FOR_DELIVERY": OrderStatus.OUT_FOR_DELIVERY,
            "DELIVERED": OrderStatus.DELIVERED,
        }
        if new_status not in mapping:
            return Response({"detail": "Invalid delivery status."}, status=status.HTTP_400_BAD_REQUEST)
        order = assignment.order
        if new_status == "DELIVERED":
            complete_delivery(order, request.user)
        else:
            if not order.can_transition_to(mapping[new_status]) and order.order_status != mapping[new_status]:
                return Response(
                    {"detail": f"Cannot move from {order.status_label} to {new_status.replace('_', ' ').title()}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            order.set_status(mapping[new_status], note="Updated via API", actor=request.user)
        assignment.update_status(new_status)
        return Response(DeliveryAssignmentSerializer(assignment).data)

    @action(detail=False, methods=["get"])
    def earnings(self, request):
        if request.user.role != "DELIVERY_BOY":
            return Response({"detail": "Delivery partner account required."}, status=status.HTTP_403_FORBIDDEN)
        today = timezone.localdate()
        queryset = DeliveryEarning.objects.filter(delivery_boy=request.user).select_related("order", "order__restaurant")
        summary = {
            "today": queryset.filter(created_at__date=today).aggregate(t=Sum("amount"))["t"] or 0,
            "total": queryset.aggregate(t=Sum("amount"))["t"] or 0,
            "completed_deliveries": queryset.values("order").distinct().count(),
        }
        return Response({"summary": summary, "entries": DeliveryEarningSerializer(queryset[:100], many=True).data})
