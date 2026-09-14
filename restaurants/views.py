"""Customer facing restaurant browsing."""

from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from menu.models import Category, FoodItem
from restaurants.models import FavoriteRestaurant, Restaurant
from reviews.models import Review


def restaurant_list(request):
    """All approved restaurants with search + filters (database driven)."""
    queryset = Restaurant.objects.approved().annotate(
        avg_rating=Avg("reviews__rating"), review_count=Count("reviews", distinct=True)
    )

    query = (request.GET.get("q") or "").strip()
    city = (request.GET.get("city") or "").strip()
    cuisine = (request.GET.get("cuisine") or "").strip()
    sort = request.GET.get("sort") or "rating"
    veg_only = request.GET.get("veg") == "on"

    if query:
        queryset = queryset.filter(
            Q(name__icontains=query) | Q(cuisine_type__icontains=query) | Q(area__icontains=query)
        ).distinct()
    if city:
        queryset = queryset.filter(city__iexact=city)
    if cuisine:
        queryset = queryset.filter(cuisine_type__icontains=cuisine)
    if veg_only:
        queryset = queryset.filter(food_items__is_veg=True, food_items__is_available=True).distinct()

    sort_map = {
        "rating": ("-rating", "-rating_count"),
        "delivery_time": ("delivery_time",),
        "delivery_fee": ("delivery_fee",),
        "newest": ("-created_at",),
        "name": ("name",),
    }
    queryset = queryset.order_by(*sort_map.get(sort, ("-rating",)))

    cuisines = set()
    for value in Restaurant.objects.approved().values_list("cuisine_type", flat=True):
        cuisines.update(c.strip() for c in (value or "").split(",") if c.strip())

    paginator = Paginator(queryset, 12)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page,
        "restaurants": page.object_list,
        "cities": Restaurant.objects.approved().values_list("city", flat=True).distinct().order_by("city"),
        "cuisines": sorted(cuisines),
        "selected": {"q": query, "city": city, "cuisine": cuisine, "sort": sort, "veg": veg_only},
        "total": queryset.count(),
    }
    return render(request, "customer/restaurants.html", context)


def restaurant_detail(request, slug):
    """Restaurant profile page: cover, menu categories and food cards."""
    queryset = Restaurant.objects.approved().select_related("owner")
    restaurant = get_object_or_404(queryset, slug=slug)

    categories = (
        Category.objects.filter(
            is_active=True,
            food_items__restaurant=restaurant,
            food_items__is_available=True,
        )
        .annotate(item_count=Count("food_items"))
        .distinct()
    )

    food_items = (
        FoodItem.objects.filter(restaurant=restaurant)
        .select_related("category")
        .order_by("category__display_order", "name")
    )

    reviews = (
        Review.objects.filter(restaurant=restaurant, is_hidden=False)
        .select_related("customer", "order")
        .order_by("-created_at")[:12]
    )

    rating_breakdown = {
        star: Review.objects.filter(restaurant=restaurant, is_hidden=False, rating=star).count()
        for star in range(5, 0, -1)
    }

    active_coupons = restaurant.coupons.filter(is_active=True).order_by("minimum_order")[:4]

    is_favorite = False
    favorite_ids = set()
    if request.user.is_authenticated:
        is_favorite = FavoriteRestaurant.objects.filter(user=request.user, restaurant=restaurant).exists()
        favorite_ids = set(
            request.user.favorite_food_items.values_list("food_item_id", flat=True)
        )

    context = {
        "restaurant": restaurant,
        "categories": categories,
        "food_items": food_items,
        "reviews": reviews,
        "rating_breakdown": rating_breakdown,
        "is_favorite": is_favorite,
        "favorite_food_ids": favorite_ids,
        "coupons": active_coupons,
        "avg_rating": restaurant.rating,
        "review_count": restaurant.rating_count,
    }
    return render(request, "customer/restaurant_detail.html", context)


@require_POST
def toggle_favorite(request, slug):
    """AJAX favourite toggle for restaurants."""
    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "message": "Please log in to save favourites."}, status=401)
    restaurant = get_object_or_404(Restaurant, slug=slug)
    favorite, created = FavoriteRestaurant.objects.get_or_create(user=request.user, restaurant=restaurant)
    if not created:
        favorite.delete()
    return JsonResponse(
        {
            "ok": True,
            "favorited": created,
            "message": f"{restaurant.name} {'added to' if created else 'removed from'} your favourites.",
        }
    )


def favorites(request):
    """My Favorites page — restaurants and dishes."""
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    restaurant_ids = FavoriteRestaurant.objects.filter(user=request.user).values_list("restaurant_id", flat=True)
    restaurants = Restaurant.objects.filter(pk__in=restaurant_ids, is_approved=True)
    food_items = (
        FoodItem.objects.filter(pk__in=request.user.favorite_food_items.values_list("food_item_id", flat=True))
        .select_related("restaurant", "category")
    )
    return render(request, "customer/favorites.html", {"restaurants": restaurants, "foods": food_items})
