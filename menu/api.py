"""Category + food item API (/api/categories/, /api/food/)."""

from django.db.models import Count, Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from menu.models import Category, FavoriteFoodItem, FoodItem
from menu.serializers import CategorySerializer, FoodItemSerializer


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        return (
            Category.objects.filter(is_active=True)
            .annotate(
                item_count=Count(
                    "food_items",
                    filter=Q(food_items__is_available=True, food_items__restaurant__is_approved=True),
                )
            )
            .order_by("display_order", "name")
        )


class FoodItemViewSet(viewsets.ReadOnlyModelViewSet):
    """Public dish catalogue with search, price and veg filters."""

    serializer_class = FoodItemSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = FoodItem.objects.available().select_related("restaurant", "category")
        params = self.request.query_params
        if params.get("search"):
            term = params["search"]
            queryset = queryset.filter(
                Q(name__icontains=term) | Q(description__icontains=term) | Q(category__name__icontains=term)
            )
        if params.get("category"):
            queryset = queryset.filter(category__slug=params["category"])
        if params.get("restaurant"):
            queryset = queryset.filter(restaurant__slug=params["restaurant"])
        if params.get("veg") in {"1", "true", "on"}:
            queryset = queryset.filter(is_veg=True)
        if params.get("max_price"):
            try:
                queryset = queryset.filter(price__lte=float(params["max_price"]))
            except ValueError:
                pass
        if params.get("recommended") in {"1", "true", "on"}:
            queryset = queryset.filter(is_recommended=True)
        ordering = params.get("ordering") or "-order_count"
        allowed = {"price", "-price", "-order_count", "name", "-rating", "-created_at"}
        return queryset.order_by(ordering if ordering in allowed else "-order_count")

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticatedOrReadOnly])
    def favorite(self, request, pk=None):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=401)
        food = self.get_object()
        favorite, created = FavoriteFoodItem.objects.get_or_create(user=request.user, food_item=food)
        if not created:
            favorite.delete()
        return Response({"favorited": created, "message": f"{food.name} {'saved' if created else 'removed'}"})
