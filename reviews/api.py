"""Review API (/api/reviews/)."""

from django.db.models import Avg
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from reviews.models import Review
from reviews.serializers import ReviewSerializer


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer

    def get_queryset(self):
        queryset = Review.objects.filter(is_hidden=False).select_related("customer", "restaurant", "order")
        if self.request.user.is_authenticated and self.request.query_params.get("mine") in {"1", "true"}:
            queryset = queryset.filter(customer=self.request.user)
        restaurant = self.request.query_params.get("restaurant")
        if restaurant:
            queryset = queryset.filter(restaurant__slug=restaurant)
        return queryset

    def get_permissions(self):
        if self.action in {"list", "retrieve"}:
            return [AllowAny()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        order = serializer.validated_data["order"]
        serializer.save(customer=self.request.user, restaurant=order.restaurant)

    def perform_update(self, serializer):
        if serializer.instance.customer_id != self.request.user.pk and not self.request.user.is_superuser:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You can only edit your own review.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.customer_id != self.request.user.pk and not self.request.user.is_superuser:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You can only delete your own review.")
        restaurant = instance.restaurant
        instance.delete()
        restaurant.recalculate_rating()

    @action(detail=False, methods=["get"])
    def summary(self, request):
        rating = request.query_params.get("restaurant")
        queryset = Review.objects.filter(is_hidden=False)
        if rating:
            queryset = queryset.filter(restaurant__slug=rating)
        return Response(
            {
                "average": queryset.aggregate(a=Avg("rating"))["a"] or 0,
                "count": queryset.count(),
                "distribution": [
                    {"stars": star, "count": queryset.filter(rating=star).count()} for star in range(5, 0, -1)
                ],
            }
        )
