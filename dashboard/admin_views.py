"""FOODIES Admin dashboard and management panels."""

from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Avg, Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import admin_required
from delivery.models import DeliveryAssignment, DeliveryBoyProfile, DeliveryEarning
from menu.models import Category, FoodItem
from offers.models import Coupon
from orders.models import Notification, Order, OrderStatus, PaymentStatus
from orders.services import assign_delivery_boy
from payments.models import Payment
from restaurants.models import Restaurant
from reviews.models import Review

from dashboard.forms import CategoryForm, CouponForm, DeliveryBoyForm, FoodItemForm, RestaurantForm

User = get_user_model()


def _revenue(queryset):
    return queryset.filter(order_status=OrderStatus.DELIVERED).aggregate(t=Sum("total_amount"))["t"] or Decimal("0.00")


@admin_required
def admin_home(request):
    """Executive dashboard with live KPIs and database-driven charts."""
    today = timezone.localdate()
    orders = Order.objects.all()
    delivered = orders.filter(order_status=OrderStatus.DELIVERED)

    stats = {
        "total_customers": User.objects.filter(role="CUSTOMER").count(),
        "total_restaurants": Restaurant.objects.count(),
        "approved_restaurants": Restaurant.objects.filter(is_approved=True).count(),
        "total_delivery_boys": User.objects.filter(role="DELIVERY_BOY").count(),
        "online_delivery_boys": DeliveryBoyProfile.objects.filter(
            availability_status=DeliveryBoyProfile.Availability.ONLINE, is_approved=True
        ).count(),
        "total_orders": orders.count(),
        "todays_orders": orders.filter(created_at__date=today).count(),
        "active_orders": orders.exclude(order_status__in=[OrderStatus.DELIVERED, OrderStatus.CANCELLED]).count(),
        "todays_revenue": _revenue(orders.filter(created_at__date=today)),
        "total_revenue": _revenue(delivered),
        "pending_approvals": Restaurant.objects.filter(is_approved=False, is_active=True).count(),
        "pending_delivery_approvals": DeliveryBoyProfile.objects.filter(is_approved=False).count(),
        "total_reviews": Review.objects.count(),
        "avg_rating": Review.objects.aggregate(a=Avg("rating"))["a"] or 0,
        "cancelled_orders": orders.filter(order_status=OrderStatus.CANCELLED).count(),
        "cod_pending": orders.filter(payment_status=PaymentStatus.COD, order_status=OrderStatus.DELIVERED).aggregate(t=Sum("total_amount"))["t"] or Decimal("0.00"),
    }
    stats["total_commission"] = (stats["total_revenue"] * Decimal("0.15")).quantize(Decimal("0.01"))
    stats["delivery_payouts"] = DeliveryEarning.objects.aggregate(t=Sum("amount"))["t"] or Decimal("0.00")

    # --- Daily orders for the last 14 days ---------------------------------- #
    daily = []
    for offset in range(13, -1, -1):
        day = today - timedelta(days=offset)
        day_orders = orders.filter(created_at__date=day)
        daily.append(
            {
                "label": day.strftime("%d %b"),
                "short": day.strftime("%d"),
                "orders": day_orders.count(),
                "revenue": float(_revenue(day_orders)),
            }
        )

    # --- Weekly revenue for the last 8 weeks -------------------------------- #
    weekly = []
    this_week_start = today - timedelta(days=today.weekday())
    for offset in range(7, -1, -1):
        start = this_week_start - timedelta(weeks=offset)
        end = start + timedelta(days=6)
        weekly.append(
            {
                "label": f"{start.strftime('%d %b')}",
                "orders": orders.filter(created_at__date__range=(start, end)).count(),
                "revenue": float(_revenue(orders.filter(created_at__date__range=(start, end)))),
            }
        )

    # --- Monthly revenue for the last 6 months ------------------------------ #
    monthly = []
    cursor = today.replace(day=1)
    months = []
    for _ in range(6):
        months.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    for month_start in reversed(months):
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        month_orders = orders.filter(created_at__date__gte=month_start, created_at__date__lt=next_month)
        monthly.append(
            {
                "label": month_start.strftime("%b %Y"),
                "orders": month_orders.count(),
                "revenue": float(_revenue(month_orders)),
            }
        )

    top_restaurants = (
        Restaurant.objects.annotate(
            order_total=Count("orders"),
            revenue=Sum("orders__total_amount", filter=Q(orders__order_status=OrderStatus.DELIVERED)),
        )
        .filter(order_total__gt=0)
        .order_by("-revenue")[:8]
    )

    popular_food = FoodItem.objects.order_by("-order_count")[:8]

    context = {
        "stats": stats,
        "daily": daily,
        "weekly": weekly,
        "monthly": monthly,
        "max_daily_orders": max([d["orders"] for d in daily] + [1]),
        "max_weekly_revenue": max([w["revenue"] for w in weekly] + [1]),
        "max_monthly_revenue": max([m["revenue"] for m in monthly] + [1]),
        "top_restaurants": top_restaurants,
        "popular_food": popular_food,
        "recent_orders": orders.select_related("customer", "restaurant")[:8],
        "pending_restaurants": Restaurant.objects.filter(is_approved=False).select_related("owner")[:5],
        "recent_reviews": Review.objects.select_related("customer", "restaurant")[:5],
        "status_split": [
            {
                "label": OrderStatus(value).label,
                "count": orders.filter(order_status=value).count(),
            }
            for value in OrderStatus.values
        ],
    }
    return render(request, "admin_console/dashboard.html", context)


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
@admin_required
def customers(request):
    queryset = User.objects.filter(role="CUSTOMER").annotate(
        order_count=Count("orders"), spent=Sum("orders__total_amount")
    )
    query = (request.GET.get("q") or "").strip()
    if query:
        queryset = queryset.filter(
            Q(email__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(phone__icontains=query)
        )
    status = request.GET.get("status")
    if status == "active":
        queryset = queryset.filter(is_active=True)
    elif status == "blocked":
        queryset = queryset.filter(is_active=False)
    return render(
        request,
        "admin_console/customers.html",
        {"customers": queryset.order_by("-date_joined")[:200], "q": query, "status": status or ""},
    )


@admin_required
def restaurant_owners(request):
    queryset = User.objects.filter(role="RESTAURANT_OWNER").annotate(restaurant_count=Count("restaurants"))
    query = (request.GET.get("q") or "").strip()
    if query:
        queryset = queryset.filter(Q(email__icontains=query) | Q(first_name__icontains=query) | Q(phone__icontains=query))
    return render(request, "admin_console/restaurant_owners.html", {"owners": queryset.order_by("-date_joined")[:200], "q": query})


@admin_required
@require_POST
def toggle_user_active(request, pk):
    """Block / unblock any account (admins cannot block themselves)."""
    user = get_object_or_404(User, pk=pk)
    if user.pk == request.user.pk:
        messages.error(request, "You cannot block your own account.")
        return redirect(request.POST.get("next") or "dashboard:admin_customers")
    user.is_active = not user.is_active
    user.blocked_reason = "" if user.is_active else (request.POST.get("reason") or "Blocked by admin")
    user.save(update_fields=["is_active", "blocked_reason"])
    if not user.is_active:
        from orders.services import notify

        notify(user, "Account blocked", user.blocked_reason, Notification.Kind.ACCOUNT)
    messages.success(request, f"{user.full_name} has been {'unblocked' if user.is_active else 'blocked'}.")
    return redirect(request.POST.get("next") or "dashboard:admin_customers")


# --------------------------------------------------------------------------- #
# Restaurants & approvals
# --------------------------------------------------------------------------- #
@admin_required
def restaurants(request):
    queryset = Restaurant.objects.select_related("owner").annotate(
        order_count=Count("orders"), revenue=Sum("orders__total_amount")
    )
    query = (request.GET.get("q") or "").strip()
    if query:
        queryset = queryset.filter(Q(name__icontains=query) | Q(city__icontains=query) | Q(owner__email__icontains=query))
    approval = request.GET.get("approval")
    if approval == "approved":
        queryset = queryset.filter(is_approved=True)
    elif approval == "pending":
        queryset = queryset.filter(is_approved=False)
    return render(
        request,
        "admin_console/restaurants.html",
        {"restaurants": queryset.order_by("-created_at")[:200], "q": query, "approval": approval or ""},
    )


@admin_required
def approvals(request):
    pending = Restaurant.objects.filter(is_approved=False).select_related("owner").order_by("created_at")
    recent = Restaurant.objects.filter(is_approved=True).select_related("owner").order_by("-updated_at")[:10]
    return render(request, "admin_console/approvals.html", {"pending": pending, "recent": recent})


@admin_required
@require_POST
def approve_restaurant(request, pk):
    restaurant = get_object_or_404(Restaurant, pk=pk)
    restaurant.is_approved = True
    restaurant.is_active = True
    restaurant.is_open = True
    restaurant.rejection_reason = ""
    restaurant.save(update_fields=["is_approved", "is_active", "is_open", "rejection_reason", "updated_at"])
    from orders.services import notify

    notify(
        restaurant.owner,
        "Restaurant approved 🎉",
        f"{restaurant.name} is now live on FOODIES and visible to customers.",
        Notification.Kind.RESTAURANT,
        "/restaurant-dashboard/",
    )
    messages.success(request, f"{restaurant.name} approved and live.")
    return redirect(request.POST.get("next") or "dashboard:admin_approvals")


@admin_required
@require_POST
def reject_restaurant(request, pk):
    restaurant = get_object_or_404(Restaurant, pk=pk)
    restaurant.is_approved = False
    restaurant.rejection_reason = (request.POST.get("reason") or "Did not meet FOODIES quality guidelines")[:255]
    restaurant.save(update_fields=["is_approved", "rejection_reason", "updated_at"])
    from orders.services import notify

    notify(
        restaurant.owner,
        "Restaurant needs changes",
        restaurant.rejection_reason,
        Notification.Kind.RESTAURANT,
        "/restaurant-dashboard/",
    )
    messages.warning(request, f"{restaurant.name} rejected.")
    return redirect(request.POST.get("next") or "dashboard:admin_approvals")


@admin_required
def restaurant_detail(request, pk):
    restaurant = get_object_or_404(Restaurant.objects.select_related("owner"), pk=pk)
    orders = restaurant.orders.select_related("customer").order_by("-created_at")[:20]
    menu_items = restaurant.food_items.select_related("category")
    return render(
        request,
        "admin_console/restaurant_detail.html",
        {
            "restaurant": restaurant,
            "orders": orders,
            "menu_items": menu_items,
            "order_count": restaurant.orders.count(),
            "revenue": restaurant.orders.filter(order_status=OrderStatus.DELIVERED).aggregate(t=Sum("total_amount"))["t"] or Decimal("0.00"),
            "reviews": restaurant.reviews.select_related("customer")[:10],
        },
    )


@admin_required
@require_POST
def toggle_restaurant_open(request, pk):
    restaurant = get_object_or_404(Restaurant, pk=pk)
    restaurant.is_open = not restaurant.is_open
    restaurant.save(update_fields=["is_open", "updated_at"])
    messages.success(request, f"{restaurant.name} is now {'open' if restaurant.is_open else 'closed'}.")
    return redirect(request.POST.get("next") or "dashboard:admin_restaurants")


# --------------------------------------------------------------------------- #
# Delivery partners
# --------------------------------------------------------------------------- #
@admin_required
def delivery_boys(request):
    queryset = User.objects.filter(role="DELIVERY_BOY").select_related("delivery_profile")
    query = (request.GET.get("q") or "").strip()
    if query:
        queryset = queryset.filter(Q(email__icontains=query) | Q(first_name__icontains=query) | Q(phone__icontains=query))
    rows = []
    for partner in queryset.order_by("-date_joined"):
        profile = getattr(partner, "delivery_profile", None)
        rows.append(
            {
                "user": partner,
                "profile": profile,
                "active": partner.deliveries.filter(
                    order_status__in=[OrderStatus.ASSIGNED, OrderStatus.PICKED_UP, OrderStatus.OUT_FOR_DELIVERY]
                ).count(),
                "completed": partner.deliveries.filter(order_status=OrderStatus.DELIVERED).count(),
                "earnings": partner.delivery_earnings.aggregate(t=Sum("amount"))["t"] or Decimal("0.00"),
            }
        )
    return render(request, "admin_console/delivery_boys.html", {"rows": rows, "q": query, "form": DeliveryBoyForm()})


@admin_required
@require_POST
def delivery_boy_create(request):
    form = DeliveryBoyForm(request.POST)
    if form.is_valid():
        data = form.cleaned_data
        user = User.objects.create_user(
            email=data["email"],
            password=data["password"],
            first_name=data["first_name"],
            last_name=data.get("last_name", ""),
            phone=data["phone"],
            role="DELIVERY_BOY",
        )
        DeliveryBoyProfile.objects.create(
            user=user,
            vehicle_type=data["vehicle_type"],
            vehicle_number=data.get("vehicle_number", ""),
            license_number=data.get("license_number", ""),
            current_area=data.get("current_area", ""),
            is_approved=data.get("is_approved", False),
            availability_status=DeliveryBoyProfile.Availability.OFFLINE,
        )
        messages.success(request, f"Delivery partner {user.full_name} created.")
    else:
        messages.error(request, "Could not create partner: " + "; ".join(f"{k}: {v[0]}" for k, v in form.errors.items()))
    return redirect("dashboard:admin_delivery_boys")


@admin_required
@require_POST
def toggle_delivery_approval(request, pk):
    profile = get_object_or_404(DeliveryBoyProfile, user__pk=pk)
    profile.is_approved = not profile.is_approved
    if not profile.is_approved:
        profile.availability_status = DeliveryBoyProfile.Availability.OFFLINE
    profile.save(update_fields=["is_approved", "availability_status", "updated_at"])
    from orders.services import notify

    notify(
        profile.user,
        "Partner account approved 🛵" if profile.is_approved else "Partner account suspended",
        "You can now go online and accept deliveries." if profile.is_approved else "Contact FOODIES support for details.",
        Notification.Kind.DELIVERY,
        "/delivery/",
    )
    messages.success(request, f"{profile.user.full_name} {'approved' if profile.is_approved else 'suspended'}.")
    return redirect("dashboard:admin_delivery_boys")


@admin_required
def delivery_assignments(request):
    """Admin delivery management: assign partners and track live deliveries."""
    ready = Order.objects.filter(order_status=OrderStatus.READY_FOR_PICKUP, delivery_boy__isnull=True).select_related("restaurant", "customer")
    active = Order.objects.filter(
        order_status__in=[OrderStatus.ASSIGNED, OrderStatus.PICKED_UP, OrderStatus.OUT_FOR_DELIVERY]
    ).select_related("restaurant", "customer", "delivery_boy")
    partners = (
        User.objects.filter(role="DELIVERY_BOY", is_active=True, delivery_profile__is_approved=True)
        .select_related("delivery_profile")
        .annotate(active_count=Count("deliveries", filter=Q(deliveries__order_status__in=[
            OrderStatus.ASSIGNED, OrderStatus.PICKED_UP, OrderStatus.OUT_FOR_DELIVERY
        ])))
        .order_by("delivery_profile__availability_status", "first_name")
    )
    history = DeliveryAssignment.objects.select_related("order", "delivery_boy").order_by("-assigned_at")[:40]
    earnings = DeliveryEarning.objects.select_related("delivery_boy", "order").order_by("-created_at")[:20]
    return render(
        request,
        "admin_console/delivery_assignments.html",
        {"ready_orders": ready, "active_orders": active, "partners": partners, "history": history, "earnings": earnings},
    )


@admin_required
@require_POST
def assign_partner(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    partner_id = request.POST.get("delivery_boy")
    partner = User.objects.filter(pk=partner_id, role="DELIVERY_BOY").first()
    try:
        assign_delivery_boy(order, partner, actor=request.user)
        messages.success(request, f"Order #{order.order_number} assigned to {partner.full_name}.")
    except ValidationError as exc:
        messages.error(request, exc.messages[0] if exc.messages else "Could not assign this order.")
    return redirect(request.POST.get("next") or "dashboard:admin_delivery_assignments")


# --------------------------------------------------------------------------- #
# Catalogue
# --------------------------------------------------------------------------- #
@admin_required
def categories(request):
    queryset = Category.objects.annotate(item_count=Count("food_items"))
    return render(
        request,
        "admin_console/categories.html",
        {"categories": queryset, "form": CategoryForm(), "editing": None},
    )


@admin_required
def category_form(request, pk=None):
    instance = get_object_or_404(Category, pk=pk) if pk else None
    if request.method == "POST":
        form = CategoryForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, f"Category {'updated' if instance else 'created'} successfully.")
            return redirect("dashboard:admin_categories")
        messages.error(request, "Please correct the category form.")
    else:
        form = CategoryForm(instance=instance)
    return render(
        request,
        "admin_console/category_form.html",
        {"form": form, "instance": instance, "categories": Category.objects.annotate(item_count=Count("food_items"))},
    )


@admin_required
@require_POST
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if category.food_items.exists():
        messages.error(request, f"{category.name} still has {category.food_items.count()} dishes. Move or delete them first.")
    else:
        category.delete()
        messages.success(request, "Category deleted.")
    return redirect("dashboard:admin_categories")


@admin_required
def food_items(request):
    queryset = FoodItem.objects.select_related("restaurant", "category")
    query = (request.GET.get("q") or "").strip()
    restaurant_id = request.GET.get("restaurant")
    if query:
        queryset = queryset.filter(Q(name__icontains=query) | Q(restaurant__name__icontains=query))
    if restaurant_id:
        queryset = queryset.filter(restaurant_id=restaurant_id)
    return render(
        request,
        "admin_console/food_items.html",
        {
            "food_items": queryset[:200],
            "restaurants": Restaurant.objects.order_by("name"),
            "q": query,
            "restaurant_id": restaurant_id or "",
        },
    )


@admin_required
@require_POST
def toggle_food_availability(request, pk):
    food = get_object_or_404(FoodItem, pk=pk)
    food.is_available = not food.is_available
    food.save(update_fields=["is_available", "updated_at"])
    messages.success(request, f"{food.name} marked {'available' if food.is_available else 'unavailable'}.")
    return redirect(request.POST.get("next") or "dashboard:admin_food_items")


@admin_required
@require_POST
def delete_food_item(request, pk):
    food = get_object_or_404(FoodItem, pk=pk)
    name = food.name
    food.delete()
    messages.success(request, f"{name} deleted from the catalogue.")
    return redirect(request.POST.get("next") or "dashboard:admin_food_items")


# --------------------------------------------------------------------------- #
# Orders, payments, coupons, reviews
# --------------------------------------------------------------------------- #
@admin_required
def orders(request):
    queryset = Order.objects.select_related("customer", "restaurant", "delivery_boy")
    status = request.GET.get("status", "")
    query = (request.GET.get("q") or "").strip()
    if status:
        queryset = queryset.filter(order_status=status)
    if query:
        queryset = queryset.filter(
            Q(order_number__icontains=query) | Q(customer__email__icontains=query) | Q(restaurant__name__icontains=query)
        )
    return render(
        request,
        "admin_console/orders.html",
        {
            "orders": queryset[:200],
            "status": status,
            "q": query,
            "statuses": OrderStatus.choices,
            "counts": {value: Order.objects.filter(order_status=value).count() for value in OrderStatus.values},
        },
    )


@admin_required
def order_detail(request, order_number):
    order = get_object_or_404(
        Order.objects.select_related("customer", "restaurant", "delivery_boy", "coupon").prefetch_related("items", "status_history", "payments"),
        order_number=order_number,
    )
    partners = User.objects.filter(role="DELIVERY_BOY", is_active=True, delivery_profile__is_approved=True)
    return render(request, "admin_console/order_detail.html", {"order": order, "partners": partners})


@admin_required
@require_POST
def update_order_status(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    new_status = request.POST.get("status")
    if not new_status or new_status not in OrderStatus.values:
        messages.error(request, "Choose a valid status.")
        return redirect("dashboard:admin_order_detail", order_number=order.order_number)
    if new_status == OrderStatus.CANCELLED:
        from orders.services import cancel_order

        try:
            cancel_order(order, actor=request.user, reason=request.POST.get("note") or "Cancelled by admin")
            messages.success(request, f"Order #{order.order_number} cancelled.")
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        return redirect("dashboard:admin_order_detail", order_number=order.order_number)

    order.set_status(new_status, note=request.POST.get("note", "Updated by admin"), actor=request.user)
    messages.success(request, f"Order #{order.order_number} updated to {order.status_label}.")
    return redirect("dashboard:admin_order_detail", order_number=order.order_number)


@admin_required
def payments(request):
    queryset = Payment.objects.select_related("order", "order__customer")
    status = request.GET.get("status")
    method = request.GET.get("method")
    if status:
        queryset = queryset.filter(status=status)
    if method:
        queryset = queryset.filter(payment_method=method)
    totals = {
        "collected": Payment.objects.filter(status=Payment.Status.SUCCESS).aggregate(t=Sum("amount"))["t"] or Decimal("0.00"),
        "pending": Payment.objects.filter(status=Payment.Status.PENDING).aggregate(t=Sum("amount"))["t"] or Decimal("0.00"),
        "failed": Payment.objects.filter(status=Payment.Status.FAILED).aggregate(t=Sum("amount"))["t"] or Decimal("0.00"),
        "cod": Payment.objects.filter(payment_method=Payment.Method.COD).aggregate(t=Sum("amount"))["t"] or Decimal("0.00"),
    }
    return render(
        request,
        "admin_console/payments.html",
        {
            "payments": queryset[:200],
            "totals": totals,
            "status": status or "",
            "method": method or "",
            "statuses": Payment.Status.choices,
            "methods": Payment.Method.choices,
        },
    )


@admin_required
def coupons(request):
    queryset = Coupon.objects.select_related("restaurant").annotate(redemptions_count=Count("redemptions"))
    return render(request, "admin_console/coupons.html", {"coupons": queryset, "form": CouponForm(), "now": timezone.now()})


@admin_required
def coupon_form(request, pk=None):
    instance = get_object_or_404(Coupon, pk=pk) if pk else None
    if request.method == "POST":
        form = CouponForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, f"Coupon {'updated' if instance else 'created'}.")
            return redirect("dashboard:admin_coupons")
        messages.error(request, "Please correct the coupon form.")
    else:
        form = CouponForm(instance=instance)
    return render(
        request,
        "admin_console/coupon_form.html",
        {"form": form, "instance": instance, "coupons": Coupon.objects.all()},
    )


@admin_required
@require_POST
def toggle_coupon(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)
    coupon.is_active = not coupon.is_active
    coupon.save(update_fields=["is_active"])
    messages.success(request, f"Coupon {coupon.code} {'activated' if coupon.is_active else 'deactivated'}.")
    return redirect("dashboard:admin_coupons")


@admin_required
@require_POST
def delete_coupon(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)
    code = coupon.code
    coupon.delete()
    messages.success(request, f"Coupon {code} deleted.")
    return redirect("dashboard:admin_coupons")


@admin_required
def reviews(request):
    queryset = Review.objects.select_related("customer", "restaurant", "order")
    rating = request.GET.get("rating")
    if rating:
        queryset = queryset.filter(rating=rating)
    return render(
        request,
        "admin_console/reviews.html",
        {
            "reviews": queryset[:200],
            "rating": rating or "",
            "avg": Review.objects.aggregate(a=Avg("rating"))["a"] or 0,
            "count": Review.objects.count(),
            "distribution": [
                {"star": star, "count": Review.objects.filter(rating=star).count()} for star in range(5, 0, -1)
            ],
        },
    )


@admin_required
@require_POST
def toggle_review_visibility(request, pk):
    review = get_object_or_404(Review, pk=pk)
    review.is_hidden = not review.is_hidden
    review.save(update_fields=["is_hidden"])
    review.restaurant.recalculate_rating()
    messages.success(request, f"Review {'hidden' if review.is_hidden else 'restored'}.")
    return redirect("dashboard:admin_reviews")


@admin_required
@require_POST
def delete_review(request, pk):
    review = get_object_or_404(Review, pk=pk)
    restaurant = review.restaurant
    review.delete()
    restaurant.recalculate_rating()
    messages.success(request, "Review deleted.")
    return redirect("dashboard:admin_reviews")


# --------------------------------------------------------------------------- #
# Reports & settings
# --------------------------------------------------------------------------- #
@admin_required
def reports(request):
    today = timezone.localdate()
    days = int(request.GET.get("days", 30))
    start = today - timedelta(days=days - 1)
    orders = Order.objects.filter(created_at__date__gte=start)

    top_restaurants = (
        Restaurant.objects.filter(orders__created_at__date__gte=start)
        .annotate(orders_count=Count("orders"), revenue=Sum("orders__total_amount"))
        .order_by("-revenue")[:10]
    )
    top_food = (
        FoodItem.objects.filter(order_items__order__created_at__date__gte=start)
        .annotate(sold=Sum("order_items__quantity"), revenue=Sum("order_items__total"))
        .order_by("-sold")[:10]
    )
    top_customers = (
        User.objects.filter(orders__created_at__date__gte=start, role="CUSTOMER")
        .annotate(orders_count=Count("orders"), spent=Sum("orders__total_amount"))
        .order_by("-spent")[:10]
    )
    partner_report = (
        User.objects.filter(role="DELIVERY_BOY")
        .annotate(deliveries_count=Count("deliveries"), payout=Sum("delivery_earnings__amount"))
        .order_by("-deliveries_count")[:10]
    )
    summary = {
        "orders": orders.count(),
        "revenue": orders.filter(order_status=OrderStatus.DELIVERED).aggregate(t=Sum("total_amount"))["t"] or Decimal("0.00"),
        "avg_order": orders.aggregate(a=Avg("total_amount"))["a"] or Decimal("0.00"),
        "cancelled": orders.filter(order_status=OrderStatus.CANCELLED).count(),
        "new_customers": User.objects.filter(role="CUSTOMER", date_joined__date__gte=start).count(),
    }
    return render(
        request,
        "admin_console/reports.html",
        {
            "days": days,
            "summary": summary,
            "top_restaurants": top_restaurants,
            "top_food": top_food,
            "top_customers": top_customers,
            "partner_report": partner_report,
        },
    )


@admin_required
def settings_view(request):
    from django.conf import settings as dj_settings

    config = {
        "Tax rate": f"{dj_settings.TAX_RATE * 100:.0f}%",
        "Platform fee": f"{dj_settings.DEFAULT_CURRENCY}{dj_settings.PLATFORM_FEE}",
        "Free delivery above": f"{dj_settings.DEFAULT_CURRENCY}{dj_settings.FREE_DELIVERY_ABOVE}",
        "Restaurant commission": f"{dj_settings.RESTAURANT_COMMISSION_RATE * 100:.0f}%",
        "Default delivery earning": f"{dj_settings.DEFAULT_CURRENCY}{dj_settings.DEFAULT_DELIVERY_EARNING}",
        "Payment gateway": "Razorpay (live keys configured)" if dj_settings.RAZORPAY_KEY_ID else "Mock / test gateway",
        "Debug mode": "On" if dj_settings.DEBUG else "Off",
        "Database": dj_settings.DATABASES["default"]["ENGINE"].split(".")[-1],
    }
    return render(request, "admin_console/settings.html", {"config": config})
