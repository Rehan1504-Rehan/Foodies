"""Public FOODIES pages: home, search, offers, static pages and error handlers."""

from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from menu.models import Category, FoodItem
from offers.models import Coupon
from restaurants.models import Restaurant

User = get_user_model()


def home(request):
    """FOODIES landing page — every block is a live database query."""
    approved = Restaurant.objects.approved().annotate(
        avg_rating=Avg("reviews__rating"), review_count=Count("reviews", distinct=True)
    )

    categories = Category.objects.filter(is_active=True).annotate(
        item_count=Count(
            "food_items",
            filter=Q(food_items__is_available=True, food_items__restaurant__is_approved=True),
        )
    )[:12]

    context = {
        "categories": categories,
        "popular_restaurants": approved.order_by("-rating_count", "-rating", "name")[:8],
        "top_rated": approved.filter(rating__gt=0).order_by("-rating", "-rating_count")[:8],
        "new_restaurants": approved.order_by("-created_at")[:8],
        "recommended": approved.annotate(order_count=Count("orders", distinct=True)).order_by("-order_count", "-rating")[:8],
        "offers": Coupon.objects.filter(is_active=True, valid_until__gte=timezone.now()).order_by("-created_at")[:6],
        "popular_food": FoodItem.objects.available()
        .select_related("restaurant", "category")
        .order_by("-order_count", "-rating")[:10],
        "featured_food": FoodItem.objects.available()
        .filter(is_recommended=True)
        .select_related("restaurant")[:8],
        "cities": list(Restaurant.objects.approved().values_list("city", flat=True).distinct().order_by("city")),
        "total_restaurants": approved.count(),
        "total_customers": User.objects.filter(role="CUSTOMER").count(),
        "total_dishes": FoodItem.objects.available().count(),
    }
    return render(request, "customer/home.html", context)


def _cuisine_choices():
    """Distinct cuisines across approved restaurants (from the database)."""
    seen = {}
    for value in Restaurant.objects.approved().values_list("cuisine_type", flat=True):
        for part in (value or "").split(","):
            name = part.strip()
            if name:
                seen.setdefault(name.lower(), name)
    return sorted(seen.values())


def search(request):
    """Search restaurants, dishes and categories using real database filters."""
    query = (request.GET.get("q") or "").strip()
    city = (request.GET.get("city") or "").strip()
    category_slug = (request.GET.get("category") or "").strip()
    veg_only = request.GET.get("veg") == "on"
    min_rating = (request.GET.get("rating") or "").strip()
    max_price = (request.GET.get("max_price") or "").strip()
    max_delivery = (request.GET.get("delivery_time") or "").strip()
    has_offer = request.GET.get("offers") == "on"
    cuisine = (request.GET.get("cuisine") or "").strip()
    sort = request.GET.get("sort") or "relevance"

    restaurants = Restaurant.objects.approved().annotate(
        avg_rating=Avg("reviews__rating"), review_count=Count("reviews", distinct=True)
    )
    foods = FoodItem.objects.available().select_related("restaurant", "category")

    if query:
        restaurants = restaurants.filter(
            Q(name__icontains=query)
            | Q(cuisine_type__icontains=query)
            | Q(area__icontains=query)
            | Q(city__icontains=query)
            | Q(description__icontains=query)
            | Q(food_items__name__icontains=query, food_items__is_available=True)
        ).distinct()
        foods = foods.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(category__name__icontains=query)
            | Q(restaurant__name__icontains=query)
            | Q(restaurant__cuisine_type__icontains=query)
        ).distinct()

    if city:
        restaurants = restaurants.filter(city__iexact=city)
        foods = foods.filter(restaurant__city__iexact=city)
    if category_slug:
        restaurants = restaurants.filter(
            food_items__category__slug=category_slug, food_items__is_available=True
        ).distinct()
        foods = foods.filter(category__slug=category_slug)
    if veg_only:
        restaurants = restaurants.filter(food_items__is_veg=True, food_items__is_available=True).distinct()
        foods = foods.filter(is_veg=True)
    if min_rating:
        try:
            restaurants = restaurants.filter(rating__gte=Decimal(min_rating))
        except (InvalidOperation, ValueError):
            pass
    if max_price:
        try:
            ceiling = Decimal(max_price)
            foods = foods.filter(
                Q(discount_price__lte=ceiling)
                | Q(discount_price__isnull=True, price__lte=ceiling)
            )
        except (InvalidOperation, ValueError):
            pass
    if max_delivery:
        try:
            restaurants = restaurants.filter(delivery_time__lte=int(max_delivery))
        except (TypeError, ValueError):
            pass
    if cuisine:
        restaurants = restaurants.filter(cuisine_type__icontains=cuisine)
        foods = foods.filter(restaurant__cuisine_type__icontains=cuisine)
    if has_offer:
        now = timezone.now()
        restaurants = restaurants.filter(
            Q(coupons__is_active=True, coupons__valid_until__gte=now)
            | Q(food_items__discount_price__isnull=False)
        ).distinct()
        foods = foods.filter(
            Q(discount_price__isnull=False)
            | Q(restaurant__coupons__is_active=True, restaurant__coupons__valid_until__gte=now)
        ).distinct()

    restaurant_sorting = {
        "rating": ("-rating", "-review_count"),
        "delivery_time": ("delivery_time", "-rating"),
        "delivery_fee": ("delivery_fee", "-rating"),
        "name": ("name",),
    }
    restaurants = restaurants.order_by(*restaurant_sorting.get(sort, ("-rating", "-rating_count", "name")))

    food_sorting = {
        "price_low": ("price",),
        "price_high": ("-price",),
    }
    foods = foods.order_by(*food_sorting.get(sort, ("-order_count", "-rating", "name")))

    context = {
        "query": query,
        "restaurants": restaurants[:40],
        "foods": foods[:40],
        "categories": Category.objects.filter(is_active=True),
        "cities": Restaurant.objects.approved().values_list("city", flat=True).distinct().order_by("city"),
        "cuisines": _cuisine_choices(),
        "selected": {
            "city": city,
            "cuisine": cuisine,
            "category": category_slug,
            "veg": veg_only,
            "rating": min_rating,
            "max_price": max_price,
            "delivery_time": max_delivery,
            "offers": has_offer,
            "sort": sort,
        },
        "restaurant_count": restaurants.count(),
        "food_count": foods.count(),
    }
    return render(request, "customer/search.html", context)


def offers(request):
    now = timezone.now()
    context = {
        "coupons": Coupon.objects.filter(is_active=True, valid_until__gte=now, valid_from__lte=now).order_by("minimum_order"),
        "upcoming": Coupon.objects.filter(is_active=True, valid_from__gt=now).order_by("valid_from"),
        "expired": Coupon.objects.filter(valid_until__lt=now).order_by("-valid_until")[:6],
        "discounted_food": FoodItem.objects.available()
        .filter(discount_price__isnull=False)
        .select_related("restaurant", "category")[:12],
    }
    return render(request, "customer/offers.html", context)


def about(request):
    return render(request, "customer/about.html")


def contact(request):
    return render(request, "customer/contact.html")


def health(request):
    """Lightweight health-check used by Render / Railway."""
    from django.db import connection

    try:
        connection.ensure_connection()
        db_ok = True
    except Exception:  # noqa: BLE001 - report unhealthy instead of crashing
        db_ok = False
    return JsonResponse({"status": "ok" if db_ok else "degraded", "service": "FOODIES", "database": db_ok})


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def error_403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def error_500(request):
    return render(request, "errors/500.html", status=500)


def error_400(request, exception=None):
    return render(request, "errors/400.html", status=400)
