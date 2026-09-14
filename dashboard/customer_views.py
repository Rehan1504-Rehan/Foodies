"""Customer account dashboard."""

from decimal import Decimal

from django.db.models import Count, Sum
from django.shortcuts import render

from accounts.permissions import customer_required
from menu.models import FavoriteFoodItem
from orders.models import Order, OrderItem, OrderStatus
from payments.models import Payment
from restaurants.models import FavoriteRestaurant


@customer_required
def customer_home(request):
    """Customer overview: live orders, spend, favourites and recommendations."""
    orders = Order.objects.filter(customer=request.user).select_related("restaurant", "delivery_boy")
    delivered = orders.filter(order_status=OrderStatus.DELIVERED)

    stats = {
        "total_orders": orders.count(),
        "active_orders": orders.exclude(order_status__in=[OrderStatus.DELIVERED, OrderStatus.CANCELLED]).count(),
        "delivered_orders": delivered.count(),
        "cancelled_orders": orders.filter(order_status=OrderStatus.CANCELLED).count(),
        "total_spent": delivered.aggregate(t=Sum("total_amount"))["t"] or Decimal("0.00"),
        "total_saved": (delivered.aggregate(t=Sum("discount"))["t"] or Decimal("0.00"))
        + (delivered.aggregate(t=Sum("coupon_discount"))["t"] or Decimal("0.00")),
        "favorite_restaurants": FavoriteRestaurant.objects.filter(user=request.user).count(),
        "favorite_foods": FavoriteFoodItem.objects.filter(user=request.user).count(),
        "addresses": request.user.addresses.count(),
        "reviews": request.user.reviews.count(),
        "payments": Payment.objects.filter(order__customer=request.user).count(),
    }

    most_ordered = (
        OrderItem.objects.filter(order__customer=request.user, food_item__isnull=False)
        .values("food_item__name", "food_item__pk", "food_item__restaurant__name", "food_item__restaurant__slug")
        .annotate(quantity=Sum("quantity"))
        .order_by("-quantity")[:4]
    )

    context = {
        "stats": stats,
        "active_orders": orders.exclude(
            order_status__in=[OrderStatus.DELIVERED, OrderStatus.CANCELLED]
        ).order_by("-created_at")[:5],
        "recent_orders": orders.order_by("-created_at")[:6],
        "favorite_restaurants": FavoriteRestaurant.objects.filter(user=request.user)
        .select_related("restaurant")[:4],
        "notifications": request.user.notifications.filter(is_read=False)[:6],
        "addresses": request.user.addresses.all()[:3],
        "most_ordered": most_ordered,
        "order_count_by_status": list(
            orders.values("order_status").annotate(count=Count("id")).order_by("-count")
        ),
    }
    return render(request, "customer/dashboard.html", context)
