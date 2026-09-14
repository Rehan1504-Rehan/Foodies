"""Food category browsing and favourite dish toggles."""

from django.db.models import Avg, Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from menu.models import Category, FavoriteFoodItem, FoodItem
from restaurants.models import Restaurant


def category_list(request):
    """All active categories with live item counts."""
    categories = Category.objects.filter(is_active=True).annotate(
        item_count=Count(
            "food_items",
            filter=Q(food_items__is_available=True, food_items__restaurant__is_approved=True),
        )
    )
    return render(request, "customer/categories.html", {"categories": categories})


def category_detail(request, slug):
    """Everything a customer can order in a category."""
    category = get_object_or_404(Category, slug=slug, is_active=True)
    restaurants = (
        Restaurant.objects.approved()
        .filter(food_items__category=category, food_items__is_available=True)
        .annotate(avg_rating=Avg("reviews__rating"))
        .distinct()
        .order_by("-rating")
    )
    foods = (
        FoodItem.objects.available()
        .filter(category=category)
        .select_related("restaurant")
        .order_by("-order_count", "name")
    )
    context = {
        "category": category,
        "restaurants": restaurants[:12],
        "foods": foods[:36],
        "restaurant_count": restaurants.count(),
        "food_count": foods.count(),
    }
    return render(request, "customer/category_detail.html", context)


@require_POST
def toggle_favorite_food(request, pk):
    """AJAX favourite toggle for a single dish."""
    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "message": "Please log in to save favourites."}, status=401)
    food = get_object_or_404(FoodItem, pk=pk)
    favorite, created = FavoriteFoodItem.objects.get_or_create(user=request.user, food_item=food)
    if not created:
        favorite.delete()
    return JsonResponse(
        {
            "ok": True,
            "favorited": created,
            "message": f"{food.name} {'added to' if created else 'removed from'} your favourites.",
        }
    )
