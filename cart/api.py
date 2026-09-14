"""Cart API (/api/cart/) — pricing always resolved server side."""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsCustomer
from cart.models import Cart
from cart.services import calculate_pricing, resolve_coupon
from menu.models import FoodItem
from offers.models import Coupon


def _cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


def _coupon_for(request):
    coupon_id = request.session.get("coupon_id")
    return Coupon.objects.filter(pk=coupon_id, is_active=True).first() if coupon_id else None


def _payload(request, cart=None, coupon=None):
    cart = cart or _cart(request.user)
    coupon = coupon if coupon is not None else _coupon_for(request)
    pricing = calculate_pricing(cart, coupon=coupon, user=request.user)
    return {
        "cart_count": cart.total_items,
        "restaurant": cart.restaurant.name if cart.restaurant else None,
        "items": [
            {
                "food_item_id": item.food_item_id,
                "name": item.food_item.name,
                "quantity": item.quantity,
                "unit_price": float(item.food_item.final_price),
                "line_total": float(item.line_total),
                "is_veg": item.food_item.is_veg,
                "image": item.food_item.image.url if item.food_item.image else None,
            }
            for item in cart.items
        ],
        "pricing": pricing.as_dict(),
        "issues": pricing.issues,
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCustomer])
def cart_detail(request):
    return Response(_payload(request))


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsCustomer])
def add_item(request):
    food_id = request.data.get("food_item") or request.data.get("food_item_id")
    food = FoodItem.objects.filter(pk=food_id).select_related("restaurant").first()
    if food is None:
        return Response({"detail": "Food item not found."}, status=status.HTTP_404_NOT_FOUND)
    if not food.is_available or not food.restaurant.is_approved or not food.restaurant.is_open:
        return Response({"detail": f"{food.name} is not available right now."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        quantity = max(1, int(request.data.get("quantity", 1)))
    except (TypeError, ValueError):
        quantity = 1
    cart = _cart(request.user)
    cart.add_item(food, quantity)
    payload = _payload(request, cart)
    payload["message"] = f"{food.name} added to your cart."
    return Response(payload, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsCustomer])
def update_item(request):
    food = FoodItem.objects.filter(pk=request.data.get("food_item") or request.data.get("food_item_id")).first()
    if food is None:
        return Response({"detail": "Food item not found."}, status=status.HTTP_404_NOT_FOUND)
    cart = _cart(request.user)
    action = request.data.get("action", "set")
    if action == "increase":
        cart.add_item(food, 1)
    elif action == "decrease":
        cart.add_item(food, -1)
    else:
        try:
            cart.set_quantity(food, int(request.data.get("quantity", 1)))
        except (TypeError, ValueError):
            return Response({"detail": "Invalid quantity."}, status=status.HTTP_400_BAD_REQUEST)
    payload = _payload(request, cart)
    payload["quantity"] = cart.quantity_of(food)
    return Response(payload)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsCustomer])
def remove_item(request):
    food = FoodItem.objects.filter(pk=request.data.get("food_item") or request.data.get("food_item_id")).first()
    if food is None:
        return Response({"detail": "Food item not found."}, status=status.HTTP_404_NOT_FOUND)
    cart = _cart(request.user)
    cart.remove_item(food)
    return Response(_payload(request, cart))


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsCustomer])
def clear(request):
    cart = _cart(request.user)
    cart.clear()
    request.session.pop("coupon_id", None)
    return Response({"message": "Cart cleared.", "cart_count": 0})


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsCustomer])
def apply_coupon(request):
    cart = _cart(request.user)
    code = request.data.get("code", "")
    coupon, message = resolve_coupon(code, request.user, cart.subtotal, cart.restaurant)
    if coupon is None:
        request.session.pop("coupon_id", None)
        return Response({"detail": message, **_payload(request, cart, coupon=None)}, status=status.HTTP_400_BAD_REQUEST)
    request.session["coupon_id"] = coupon.pk
    payload = _payload(request, cart, coupon=coupon)
    payload["message"] = message
    return Response(payload)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsCustomer])
def remove_coupon(request):
    request.session.pop("coupon_id", None)
    return Response(_payload(request, cart=_cart(request.user), coupon=None))
