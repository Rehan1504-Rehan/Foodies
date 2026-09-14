"""Customer order history, tracking, cancellation and reorder."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import customer_required
from cart.models import Cart, CartItem
from orders.models import Order, OrderStatus
from orders.services import cancel_order


def _customer_orders(user):
    return Order.objects.filter(customer=user).select_related("restaurant", "delivery_boy", "coupon")


@customer_required
def order_list(request):
    """My Orders with status filters and pagination."""
    queryset = _customer_orders(request.user)
    status_filter = request.GET.get("status", "")
    if status_filter == "active":
        queryset = queryset.exclude(order_status__in=[OrderStatus.DELIVERED, OrderStatus.CANCELLED])
    elif status_filter == "completed":
        queryset = queryset.filter(order_status=OrderStatus.DELIVERED)
    elif status_filter == "cancelled":
        queryset = queryset.filter(order_status=OrderStatus.CANCELLED)
    elif status_filter:
        queryset = queryset.filter(order_status=status_filter)

    paginator = Paginator(queryset, 10)
    page = paginator.get_page(request.GET.get("page"))
    context = {
        "page_obj": page,
        "orders": page.object_list,
        "status_filter": status_filter,
        "active_count": _customer_orders(request.user).exclude(order_status__in=[OrderStatus.DELIVERED, OrderStatus.CANCELLED]).count(),
        "completed_count": _customer_orders(request.user).filter(order_status=OrderStatus.DELIVERED).count(),
        "cancelled_count": _customer_orders(request.user).filter(order_status=OrderStatus.CANCELLED).count(),
    }
    return render(request, "customer/orders.html", context)


@customer_required
def order_detail(request, order_number):
    """A customer can only ever open their own order (server side scoping)."""
    order = get_object_or_404(
        _customer_orders(request.user).prefetch_related("items", "status_history", "payments"),
        order_number=order_number,
    )
    return render(
        request,
        "customer/order_detail.html",
        {
            "order": order,
            "steps": order.tracking_steps,
            "payment": order.payments.order_by("-created_at").first(),
            "can_review": order.can_review,
        },
    )


@customer_required
def order_track(request, order_number):
    order = get_object_or_404(_customer_orders(request.user), order_number=order_number)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse(
            {
                "ok": True,
                "status": order.order_status,
                "status_label": order.status_label,
                "progress": order.progress_percent,
                "delivery_boy": order.delivery_partner_name,
                "steps": [
                    {"label": label, "state": state, "at": history.created_at.isoformat() if history else None}
                    for label, state, history in order.tracking_steps
                ],
            }
        )
    return render(request, "customer/order_track.html", {"order": order, "steps": order.tracking_steps})


@customer_required
@require_POST
def order_cancel(request, order_number):
    order = get_object_or_404(_customer_orders(request.user), order_number=order_number)
    reason = (request.POST.get("reason") or "Cancelled by customer").strip()[:255]
    try:
        cancel_order(order, actor=request.user, reason=reason)
        messages.success(request, f"Order #{order.order_number} has been cancelled.")
    except ValidationError as exc:
        messages.error(request, exc.messages[0] if exc.messages else "This order cannot be cancelled.")
    return redirect("orders:detail", order_number=order.order_number)


@customer_required
@require_POST
def reorder(request, order_number):
    """Rebuild the cart from a past order, skipping unavailable dishes."""
    order = get_object_or_404(_customer_orders(request.user), order_number=order_number)
    cart, _ = Cart.objects.get_or_create(user=request.user)

    if cart.restaurant and cart.restaurant_id != order.restaurant_id:
        cart.clear()

    added, skipped = 0, []
    with transaction.atomic():
        for item in order.items.select_related("food_item"):
            food = item.food_item
            if food is None or not food.is_available or not food.restaurant.is_approved:
                skipped.append(item.food_name)
                continue
            cart.add_item(food, item.quantity)
            added += 1

    if added:
        messages.success(request, f"{added} item(s) from order #{order.order_number} added back to your cart.")
    if skipped:
        messages.warning(request, "Currently unavailable: " + ", ".join(skipped))
    if not added:
        messages.error(request, "None of the items from that order are available right now.")
        return redirect("orders:detail", order_number=order.order_number)
    return redirect("cart:detail")


@customer_required
def order_invoice(request, order_number):
    order = get_object_or_404(
        _customer_orders(request.user).prefetch_related("items", "payments"), order_number=order_number
    )
    return render(request, "customer/invoice.html", {"order": order, "payment": order.payments.first()})
