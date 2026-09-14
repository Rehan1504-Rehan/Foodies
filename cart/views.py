"""Cart views — all mutations go through the database and are priced server-side."""

from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import customer_required
from cart.models import Cart
from cart.services import calculate_pricing, resolve_coupon
from menu.models import FoodItem
from offers.models import Coupon


def get_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


def _is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("accept", "")


def _cart_payload(request):
    cart = get_cart(request.user)
    coupon = None
    coupon_id = request.session.get("coupon_id")
    if coupon_id:
        coupon = Coupon.objects.filter(pk=coupon_id, is_active=True).first()
    pricing = calculate_pricing(cart, coupon=coupon, user=request.user, require_available=False)
    return cart, pricing


@customer_required
def cart_detail(request):
    cart, pricing = _cart_payload(request)
    now = timezone.now()
    active_coupons = (
        Coupon.objects.filter(is_active=True, valid_from__lte=now, valid_until__gte=now)
        .filter(Q(restaurant__isnull=True) | Q(restaurant=cart.restaurant))
        .order_by("minimum_order")[:6]
    )
    return render(request, "customer/cart.html", {"cart": cart, "pricing": pricing, "active_coupons": active_coupons})


@customer_required
@require_POST
def add_to_cart(request, pk):
    """Add a dish; handled both as AJAX and as a normal form post."""
    food = get_object_or_404(FoodItem, pk=pk)
    if not food.is_available or not food.restaurant.is_approved:
        payload = {"ok": False, "message": f"{food.name} is currently unavailable."}
        return JsonResponse(payload, status=400) if _is_ajax(request) else _redirect_with(request, payload["message"], "error")
    if not food.restaurant.is_open:
        payload = {"ok": False, "message": f"{food.restaurant.name} is closed right now."}
        return JsonResponse(payload, status=400) if _is_ajax(request) else _redirect_with(request, payload["message"], "error")

    try:
        quantity = max(1, int(request.POST.get("quantity", 1)))
    except (TypeError, ValueError):
        quantity = 1

    cart = get_cart(request.user)
    cart.add_item(food, quantity)
    cart, pricing = _cart_payload(request)

    if _is_ajax(request):
        return JsonResponse(
            {
                "ok": True,
                "message": f"{food.name} added to your cart.",
                "cart_count": cart.total_items,
                "quantity": cart.quantity_of(food),
                "pricing": pricing.as_dict(),
            }
        )
    messages.success(request, f"{food.name} added to your cart.")
    return redirect(request.POST.get("next") or "cart:detail")


@customer_required
@require_POST
def update_cart_item(request, pk):
    """Increase / decrease / set quantity — price always recalculated server-side."""
    food = get_object_or_404(FoodItem, pk=pk)
    cart = get_cart(request.user)

    action = request.POST.get("action", "set")
    if action == "increase":
        cart.add_item(food, 1)
    elif action == "decrease":
        cart.add_item(food, -1)
    else:
        try:
            quantity = int(request.POST.get("quantity", 1))
        except (TypeError, ValueError):
            quantity = 1
        cart.set_quantity(food, quantity)

    cart, pricing = _cart_payload(request)
    quantity = cart.quantity_of(food)

    if _is_ajax(request):
        item = cart.cart_items.filter(food_item=food).first()
        return JsonResponse(
            {
                "ok": True,
                "quantity": quantity,
                "removed": quantity == 0,
                "line_total": float(item.line_total) if item else 0,
                "cart_count": cart.total_items,
                "pricing": pricing.as_dict(),
            }
        )
    return redirect("cart:detail")


@customer_required
@require_POST
def remove_from_cart(request, pk):
    food = get_object_or_404(FoodItem, pk=pk)
    cart = get_cart(request.user)
    cart.remove_item(food)
    _, pricing = _cart_payload(request)
    if _is_ajax(request):
        return JsonResponse({"ok": True, "cart_count": get_cart(request.user).total_items, "pricing": pricing.as_dict()})
    messages.success(request, f"{food.name} removed from cart.")
    return redirect("cart:detail")


@customer_required
@require_POST
def clear_cart(request):
    cart = get_cart(request.user)
    cart.clear()
    request.session.pop("coupon_id", None)
    if _is_ajax(request):
        return JsonResponse({"ok": True, "cart_count": 0})
    messages.success(request, "Cart cleared.")
    return redirect("cart:detail")


@customer_required
@require_POST
def apply_coupon(request):
    """Server side coupon validation and application."""
    code = (request.POST.get("code") or "").strip()
    cart, _ = _cart_payload(request)
    subtotal = cart.subtotal
    restaurant = cart.restaurant
    coupon, message = resolve_coupon(code, request.user, subtotal, restaurant)

    if coupon is None:
        request.session.pop("coupon_id", None)
        if _is_ajax(request):
            return JsonResponse({"ok": False, "message": message, "pricing": calculate_pricing(cart, user=request.user).as_dict()}, status=400)
        messages.error(request, message)
        return redirect("cart:detail")

    request.session["coupon_id"] = coupon.pk
    pricing = calculate_pricing(cart, coupon=coupon, user=request.user)
    if _is_ajax(request):
        return JsonResponse({"ok": True, "message": message, "code": coupon.code, "pricing": pricing.as_dict()})
    messages.success(request, message)
    return redirect("cart:detail")


@customer_required
@require_POST
def remove_coupon(request):
    request.session.pop("coupon_id", None)
    cart, pricing = _cart_payload(request)
    if _is_ajax(request):
        return JsonResponse({"ok": True, "message": "Coupon removed.", "pricing": pricing.as_dict()})
    messages.info(request, "Coupon removed.")
    return redirect("cart:detail")


@customer_required
def cart_summary_api(request):
    """JSON pricing used by the checkout page to stay in sync."""
    _, pricing = _cart_payload(request)
    return JsonResponse({"ok": True, "cart_count": get_cart(request.user).total_items, "pricing": pricing.as_dict()})


def _redirect_with(request, message, level="success"):
    getattr(messages, level)(request, message)
    return redirect(request.POST.get("next") or "cart:detail")
