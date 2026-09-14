"""Restaurant API (/api/restaurants/...)."""

from django.db.models import Avg, Count, Q
from rest_framework import status, viewsets
from rest_framework.decorators import action, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from menu.models import FoodItem
from menu.serializers import FoodItemSerializer
from restaurants.models import FavoriteRestaurant, Restaurant
from restaurants.serializers import RestaurantDetailSerializer, RestaurantListSerializer


class RestaurantViewSet(viewsets.ReadOnlyModelViewSet):
    """Public, read-only restaurant catalogue with live filters."""

    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        queryset = Restaurant.objects.approved().annotate(
            avg_rating=Avg("reviews__rating"), review_count=Count("reviews", distinct=True)
        )
        params = self.request.query_params
        if params.get("search"):
            term = params["search"]
            queryset = queryset.filter(
                Q(name__icontains=term) | Q(cuisine_type__icontains=term) | Q(area__icontains=term)
            )
        if params.get("city"):
            queryset = queryset.filter(city__iexact=params["city"])
        if params.get("cuisine"):
            queryset = queryset.filter(cuisine_type__icontains=params["cuisine"])
        if params.get("veg") in {"1", "true", "on"}:
            queryset = queryset.filter(food_items__is_veg=True).distinct()
        if params.get("open") in {"1", "true", "on"}:
            queryset = queryset.filter(is_open=True)
        if params.get("min_rating"):
            try:
                queryset = queryset.filter(rating__gte=float(params["min_rating"]))
            except ValueError:
                pass
        ordering = params.get("ordering") or "-rating"
        allowed = {"-rating", "rating", "delivery_time", "-delivery_time", "delivery_fee", "-delivery_fee", "name"}
        return queryset.order_by(ordering if ordering in allowed else "-rating")

    def get_serializer_class(self):
        return RestaurantDetailSerializer if self.action == "retrieve" else RestaurantListSerializer

    @action(detail=True, methods=["get"], url_path="menu")
    def menu(self, request, slug=None):
        restaurant = self.get_object()
        items = FoodItem.objects.filter(restaurant=restaurant, is_available=True).select_related("category")
        category = request.query_params.get("category")
        if category:
            items = items.filter(category__slug=category)
        return Response(
            {
                "restaurant": RestaurantListSerializer(restaurant).data,
                "items": FoodItemSerializer(items, many=True, context={"request": request}).data,
            }
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def favorite(self, request, slug=None):
        restaurant = self.get_object()
        favorite, created = FavoriteRestaurant.objects.get_or_create(user=request.user, restaurant=restaurant)
        if not created:
            favorite.delete()
        return Response(
            {"favorited": created, "message": f"{restaurant.name} {'saved' if created else 'removed'}"},
            status=status.HTTP_200_OK,
        )
