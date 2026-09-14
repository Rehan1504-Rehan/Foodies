"""Coupon / offer API (/api/offers/)."""

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from cart.models import Cart
from cart.services import calculate_pricing, resolve_coupon
from offers.models import Coupon
from offers.serializers import CouponSerializer


class CouponViewSet(viewsets.ReadOnlyModelViewSet):
    """Active, public offers. Codes are validated server side at checkout."""

    serializer_class = CouponSerializer
    permission_classes = [AllowAny]
    lookup_field = "code"

    def get_queryset(self):
        now = timezone.now()
        queryset = Coupon.objects.filter(is_active=True, valid_from__lte=now, valid_until__gte=now)
        queryset = queryset.annotate(redemptions_count=Count("redemptions"))
        if self.request.query_params.get("restaurant"):
            queryset = queryset.filter(restaurant__slug=self.request.query_params["restaurant"])
        return queryset.order_by("minimum_order")

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def validate(self, request, code=None):
        """Validate a coupon against the requesting customer's live cart."""
        coupon = self.get_object()
        cart = Cart.objects.filter(user=request.user).first()
        subtotal = cart.subtotal if cart else 0
        restaurant = cart.restaurant if cart else None
        ok, message = coupon.validate_for(request.user, subtotal, restaurant)
        if not ok:
            return Response({"valid": False, "detail": message}, status=400)
        return Response(
            {
                "valid": True,
                "detail": message,
                "discount": float(coupon.calculate_discount(subtotal)),
                "subtotal": float(subtotal),
            }
        )
