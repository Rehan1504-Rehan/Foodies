"""Restaurant Owner dashboard and management panels.

Every query is scoped to ``request.restaurant`` (resolved in middleware from the
logged-in owner) so an owner can only ever touch their own kitchen.
"""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings as dj_settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Avg, Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.forms import ProfileForm
from accounts.permissions import restaurant_required
from menu.models import Category, FoodItem
from offers.models import Coupon
from orders.models import Order, OrderStatus
from restaurants.models import Restaurant
from reviews.models import Review

from dashboard.forms import CategoryForm, CouponForm, FoodItemForm, RestaurantForm


def _my_restaurant(request):
    return request.restaurant


def _scoped_orders(request):
    restaurant = _my_restaurant(request)
    if restaurant is None:
        return Order.objects.none()
    return Order.objects.filter(restaurant=restaurant)


@restaurant_required
def restaurant_home(request):
    """Restaurant dashboard KPIs, live orders and sales insights."""
    restaurant = _my_restaurant(request)
    if restaurant is None:
        return redirect("dashboard:restaurant_restaurant_create")

    today = timezone.localdate()
    orders = _scoped_orders(request)
    delivered = orders.filter(order_status=OrderStatus.DELIVERED)

    stats = {
        "todays_orders": orders.filter(created_at__date=today).count(),
        "pending_orders": orders.exclude(order_status__in=[OrderStatus.DELIVERED, OrderStatus.CANCELLED]).count(),
        "todays_revenue": delivered.filter(delivered_at__date=today).aggregate(t=Sum("total_amount"))["t"] or Decimal("0.00"),
        "total_revenue": delivered.aggregate(t=Sum("total_amount"))["t"] or Decimal("0.00"),
        "total_orders": orders.count(),
        "delivered_orders": delivered.count(),
        "cancelled_orders": orders.filter(order_status=OrderStatus.CANCELLED).count(),
        "avg_order_value": orders.aggregate(a=Avg("total_amount"))["a"] or Decimal("0.00"),
        "menu_items": restaurant.food_items.count(),
        "available_items": restaurant.food_items.filter(is_available=True).count(),
        "rating": restaurant.rating,
        "review_count": restaurant.rating_count,
        "payout": (delivered.aggregate(t=Sum("total_amount"))["t"] or Decimal("0.00"))
        * Decimal(str(1 - dj_settings.RESTAURANT_COMMISSION_RATE)),
    }

    popular_food = (
        restaurant.food_items.annotate(sold=Sum("order_items__quantity")).order_by("-sold", "-order_count")[:6]
    )

    # 7 day sales chart from the database.
    chart = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        day_orders = orders.filter(created_at__date=day)
        chart.append(
            {
                "label": day.strftime("%a"),
                "date": day.strftime("%d %b"),
                "orders": day_orders.count(),
                "revenue": float(day_orders.filter(order_status=OrderStatus.DELIVERED).aggregate(t=Sum("total_amount"))["t"] or 0),
            }
        )

    context = {
        "restaurant": restaurant,
        "stats": stats,
        "popular_food": popular_food,
        "chart": chart,
        "max_revenue": max([c["revenue"] for c in chart] + [1]),
        "new_orders": orders.filter(order_status=OrderStatus.PLACED).select_related("customer")[:6],
        "active_orders": orders.filter(
            order_status__in=[
                OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY_FOR_PICKUP,
                OrderStatus.ASSIGNED, OrderStatus.PICKED_UP, OrderStatus.OUT_FOR_DELIVERY,
            ]
        ).select_related("customer", "delivery_boy")[:10],
        "recent_reviews": restaurant.reviews.select_related("customer")[:5],
        "low_stock": restaurant.food_items.filter(is_available=False)[:5],
        "status_counts": {value: orders.filter(order_status=value).count() for value in OrderStatus.values},
    }
    return render(request, "restaurant/dashboard.html", context)


@restaurant_required
def restaurant_profile(request):
    """Create or edit the restaurant profile, logo and cover image."""
    restaurant = _my_restaurant(request)
    if request.method == "POST":
        form = RestaurantForm(request.POST, request.FILES, instance=restaurant)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.owner = request.user
            instance.save()
            messages.success(request, "Restaurant profile saved.")
            if not instance.is_approved:
                messages.info(request, "Your restaurant is pending FOODIES admin approval before customers can see it.")
            return redirect("dashboard:restaurant_profile")
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = RestaurantForm(instance=restaurant)
    return render(
        request,
        "restaurant/restaurant_form.html",
        {
            "form": form,
            "restaurant": restaurant,
            "reviews": restaurant.reviews.select_related("customer")[:6] if restaurant else [],
        },
    )


@restaurant_required
def restaurant_create(request):
    return redirect("dashboard:restaurant_profile")


# --------------------------------------------------------------------------- #
# Menu
# --------------------------------------------------------------------------- #
@restaurant_required
def menu_items(request):
    restaurant = _my_restaurant(request)
    if restaurant is None:
        return redirect("dashboard:restaurant_restaurant_create")
    queryset = restaurant.food_items.select_related("category")
    category_id = request.GET.get("category")
    availability = request.GET.get("availability")
    query = (request.GET.get("q") or "").strip()
    if category_id:
        queryset = queryset.filter(category_id=category_id)
    if availability == "available":
        queryset = queryset.filter(is_available=True)
    elif availability == "unavailable":
        queryset = queryset.filter(is_available=False)
    if query:
        queryset = queryset.filter(Q(name__icontains=query) | Q(description__icontains=query))
    return render(
        request,
        "restaurant/menu_items.html",
        {
            "restaurant": restaurant,
            "food_items": queryset,
            "categories": Category.objects.filter(is_active=True),
            "selected": {"category": category_id or "", "availability": availability or "", "q": query},
        },
    )


@restaurant_required
def food_item_form(request, pk=None):
    restaurant = _my_restaurant(request)
    if restaurant is None:
        return redirect("dashboard:restaurant_restaurant_create")
    # Ownership check: the item must belong to this restaurant.
    instance = get_object_or_404(FoodItem, pk=pk, restaurant=restaurant) if pk else None
    if request.method == "POST":
        form = FoodItemForm(request.POST, request.FILES, instance=instance, restaurant=restaurant)
        if form.is_valid():
            form.save()
            messages.success(request, f"Dish {'updated' if instance else 'added'} successfully.")
            return redirect("dashboard:restaurant_menu")
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = FoodItemForm(instance=instance, restaurant=restaurant)
    return render(request, "restaurant/food_item_form.html", {"form": form, "instance": instance, "restaurant": restaurant})


@restaurant_required
@require_POST
def toggle_food_availability(request, pk):
    restaurant = _my_restaurant(request)
    food = get_object_or_404(FoodItem, pk=pk, restaurant=restaurant)
    food.is_available = not food.is_available
    food.save(update_fields=["is_available", "updated_at"])
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        from django.http import JsonResponse

        return JsonResponse({"ok": True, "is_available": food.is_available})
    messages.success(request, f"{food.name} is now {'available' if food.is_available else 'unavailable'}.")
    return redirect(request.POST.get("next") or "dashboard:restaurant_menu")


@restaurant_required
@require_POST
def delete_food_item(request, pk):
    restaurant = _my_restaurant(request)
    food = get_object_or_404(FoodItem, pk=pk, restaurant=restaurant)
    name = food.name
    food.delete()
    messages.success(request, f"{name} removed from your menu.")
    return redirect("dashboard:restaurant_menu")


@restaurant_required
def categories(request):
    restaurant = _my_restaurant(request)
    if restaurant is None:
        return redirect("dashboard:restaurant_restaurant_create")
    used = Category.objects.filter(food_items__restaurant=restaurant).annotate(
        restaurant_items=Count("food_items", filter=Q(food_items__restaurant=restaurant))
    ).distinct()
    if request.method == "POST":
        form = CategoryForm(request.POST, request.FILES)
        if form.is_valid():
            category = form.save()
            messages.success(request, f"Category “{category.name}” is ready to use.")
            return redirect("dashboard:restaurant_categories")
        messages.error(request, "Could not create that category.")
    else:
        form = CategoryForm()
    return render(request, "restaurant/categories.html", {"restaurant": restaurant, "categories": used, "form": form})


@restaurant_required
@require_POST
def toggle_restaurant_open(request):
    restaurant = _my_restaurant(request)
    if restaurant is None:
        return redirect("dashboard:restaurant_restaurant_create")
    restaurant.is_open = not restaurant.is_open
    restaurant.save(update_fields=["is_open", "updated_at"])
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        from django.http import JsonResponse

        return JsonResponse({"ok": True, "is_open": restaurant.is_open})
    messages.success(request, f"Your restaurant is now {'accepting orders' if restaurant.is_open else 'closed'}.")
    return redirect(request.POST.get("next") or "dashboard:restaurant_home")


# --------------------------------------------------------------------------- #
# Orders
# --------------------------------------------------------------------------- #
@restaurant_required
def orders(request):
    restaurant = _my_restaurant(request)
    if restaurant is None:
        return redirect("dashboard:restaurant_restaurant_create")
    queryset = _scoped_orders(request).select_related("customer", "delivery_boy")
    status = request.GET.get("status", "active")
    if status == "new":
        queryset = queryset.filter(order_status=OrderStatus.PLACED)
    elif status == "preparing":
        queryset = queryset.filter(order_status__in=[OrderStatus.CONFIRMED, OrderStatus.PREPARING])
    elif status == "ready":
        queryset = queryset.filter(order_status=OrderStatus.READY_FOR_PICKUP)
    elif status == "completed":
        queryset = queryset.filter(order_status=OrderStatus.DELIVERED)
    elif status == "cancelled":
        queryset = queryset.filter(order_status=OrderStatus.CANCELLED)
    elif status == "active":
        queryset = queryset.exclude(order_status__in=[OrderStatus.DELIVERED, OrderStatus.CANCELLED])

    scoped = _scoped_orders(request)
    counts = {value: scoped.filter(order_status=value).count() for value in OrderStatus.values}
    active_count = scoped.exclude(
        order_status__in=[OrderStatus.DELIVERED, OrderStatus.CANCELLED]
    ).count()
    return render(
        request,
        "restaurant/orders.html",
        {
            "restaurant": restaurant,
            "orders": queryset[:200],
            "status": status,
            "counts": counts,
            "active_count": active_count,
            "statuses": OrderStatus.choices,
        },
    )


@restaurant_required
def order_detail(request, order_number):
    restaurant = _my_restaurant(request)
    order = get_object_or_404(
        _scoped_orders(request).prefetch_related("items", "status_history"),
        order_number=order_number,
    )
    return render(request, "restaurant/order_detail.html", {"order": order, "restaurant": restaurant})


@restaurant_required
@require_POST
def order_action(request, order_number, action):
    """Accept / reject / start preparing / mark ready for pickup."""
    order = get_object_or_404(_scoped_orders(request), order_number=order_number)

    action_map = {
        "accept": (OrderStatus.CONFIRMED, "Order accepted. Start cooking!"),
        "preparing": (OrderStatus.PREPARING, "Order marked as preparing."),
        "ready": (OrderStatus.READY_FOR_PICKUP, "Order is ready for pickup — waiting for a delivery partner."),
    }
    if action == "reject":
        from orders.services import cancel_order

        reason = request.POST.get("reason") or f"Rejected by {order.restaurant.name}"
        try:
            cancel_order(order, actor=request.user, reason=reason[:255])
            messages.warning(request, f"Order #{order.order_number} rejected and the customer has been notified.")
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if exc.messages else "Could not reject this order.")
        return redirect(request.POST.get("next") or "dashboard:restaurant_orders")

    if action not in action_map:
        messages.error(request, "Unknown order action.")
        return redirect("dashboard:restaurant_orders")

    new_status, note = action_map[action]
    if not order.can_transition_to(new_status):
        messages.error(request, f"Order #{order.order_number} cannot move to {new_status.replace('_', ' ').title()} from {order.status_label}.")
        return redirect(request.POST.get("next") or "dashboard:restaurant_orders")

    order.set_status(new_status, note=note, actor=request.user)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        from django.http import JsonResponse

        return JsonResponse({"ok": True, "status": order.order_status, "label": order.status_label})
    messages.success(request, note)
    return redirect(request.POST.get("next") or "dashboard:restaurant_orders")


# --------------------------------------------------------------------------- #
# Reviews, offers, sales, profile
# --------------------------------------------------------------------------- #
@restaurant_required
def reviews(request):
    restaurant = _my_restaurant(request)
    if restaurant is None:
        return redirect("dashboard:restaurant_restaurant_create")
    queryset = restaurant.reviews.select_related("customer", "order")
    rating = request.GET.get("rating")
    if rating:
        queryset = queryset.filter(rating=rating)
    return render(
        request,
        "restaurant/reviews.html",
        {
            "restaurant": restaurant,
            "reviews": queryset[:100],
            "rating": rating or "",
            "distribution": [
                {"star": star, "count": restaurant.reviews.filter(rating=star).count()} for star in range(5, 0, -1)
            ],
            "avg": restaurant.reviews.aggregate(a=Avg("rating"))["a"] or 0,
        },
    )


@restaurant_required
@require_POST
def reply_review(request, pk):
    restaurant = _my_restaurant(request)
    review = get_object_or_404(Review, pk=pk, restaurant=restaurant)
    review.reply = (request.POST.get("reply") or "").strip()[:600]
    review.save(update_fields=["reply", "updated_at"])
    messages.success(request, "Reply published.")
    return redirect("dashboard:restaurant_reviews")


@restaurant_required
def coupons(request):
    restaurant = _my_restaurant(request)
    if restaurant is None:
        return redirect("dashboard:restaurant_restaurant_create")
    if request.method == "POST":
        form = CouponForm(request.POST, restaurant=restaurant)
        if form.is_valid():
            coupon = form.save(commit=False)
            coupon.restaurant = restaurant
            coupon.save()
            messages.success(request, f"Offer {coupon.code} created.")
            return redirect("dashboard:restaurant_offers")
        messages.error(request, "Please correct the offer form: " + "; ".join(f"{k}: {v[0]}" for k, v in form.errors.items()))
    else:
        form = CouponForm(restaurant=restaurant, initial={"valid_from": timezone.now(), "valid_until": timezone.now() + timedelta(days=30)})
    return render(
        request,
        "restaurant/offers.html",
        {"restaurant": restaurant, "coupons": restaurant.coupons.order_by("-created_at"), "form": form, "now": timezone.now()},
    )


@restaurant_required
@require_POST
def toggle_coupon(request, pk):
    restaurant = _my_restaurant(request)
    coupon = get_object_or_404(Coupon, pk=pk)
    if coupon.restaurant_id not in (None, getattr(restaurant, "pk", None)):
        raise ValidationError("That offer belongs to another restaurant.")
    coupon.is_active = not coupon.is_active
    coupon.save(update_fields=["is_active"])
    messages.success(request, f"Offer {coupon.code} {'activated' if coupon.is_active else 'paused'}.")
    return redirect("dashboard:restaurant_offers")


@restaurant_required
def sales(request):
    restaurant = _my_restaurant(request)
    if restaurant is None:
        return redirect("dashboard:restaurant_restaurant_create")
    today = timezone.localdate()
    days = int(request.GET.get("days", 30))
    start = today - timedelta(days=days - 1)
    orders = _scoped_orders(request).filter(created_at__date__gte=start)
    delivered = orders.filter(order_status=OrderStatus.DELIVERED)

    daily = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        day_orders = orders.filter(created_at__date=day)
        daily.append(
            {
                "label": day.strftime("%d %b"),
                "orders": day_orders.count(),
                "revenue": float(day_orders.filter(order_status=OrderStatus.DELIVERED).aggregate(t=Sum("total_amount"))["t"] or 0),
            }
        )

    top_items = (
        FoodItem.objects.filter(restaurant=restaurant, order_items__order__created_at__date__gte=start)
        .annotate(sold=Sum("order_items__quantity"), revenue=Sum("order_items__total"))
        .order_by("-sold")[:10]
    )

    gross = delivered.aggregate(t=Sum("total_amount"))["t"] or Decimal("0.00")
    summary = {
        "gross": gross,
        "commission": (gross * Decimal(str(dj_settings.RESTAURANT_COMMISSION_RATE))).quantize(Decimal("0.01")),
        "payout": (gross * Decimal(str(1 - dj_settings.RESTAURANT_COMMISSION_RATE))).quantize(Decimal("0.01")),
        "orders": orders.count(),
        "delivered": delivered.count(),
        "cancelled": orders.filter(order_status=OrderStatus.CANCELLED).count(),
        "avg_order": orders.aggregate(a=Avg("total_amount"))["a"] or Decimal("0.00"),
    }
    return render(
        request,
        "restaurant/sales.html",
        {
            "restaurant": restaurant,
            "daily": daily,
            "max_revenue": max([d["revenue"] for d in daily] + [1]),
            "top_items": top_items,
            "summary": summary,
            "days": days,
        },
    )


@restaurant_required
def profile_settings(request):
    """Owner account settings (name, phone, photo, password)."""
    form = ProfileForm(instance=request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Account updated.")
            return redirect("dashboard:restaurant_profile_settings")
        messages.error(request, "Please correct the errors below.")
    return render(
        request,
        "restaurant/profile_settings.html",
        {"form": form, "restaurant": _my_restaurant(request)},
    )
