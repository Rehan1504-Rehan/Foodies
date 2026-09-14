"""Cart pricing engine.

Every money value shown to a customer is calculated here, on the server.
Prices, discounts, taxes and coupons sent by the browser are never trusted.
"""

from dataclasses import dataclass, field, asdict
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

TWO_PLACES = Decimal("0.01")


def money(value) -> Decimal:
    """Round any numeric input to 2 decimal places (banker-safe half-up)."""
    if value is None:
        value = Decimal("0")
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass
class PriceBreakdown:
    item_count: int = 0
    mrp_total: Decimal = Decimal("0.00")
    subtotal: Decimal = Decimal("0.00")
    food_discount: Decimal = Decimal("0.00")
    delivery_fee: Decimal = Decimal("0.00")
    tax: Decimal = Decimal("0.00")
    platform_fee: Decimal = Decimal("0.00")
    coupon_code: str = ""
    coupon_discount: Decimal = Decimal("0.00")
    total: Decimal = Decimal("0.00")
    free_delivery_gap: Decimal = Decimal("0.00")
    restaurant: object = None
    coupon_message: str = ""
    coupon_applied: bool = False
    issues: list = field(default_factory=list)

    @property
    def total_savings(self):
        return money(self.food_discount + self.coupon_discount)

    @property
    def tax_percent(self):
        return round(settings.TAX_RATE * 100)

    def as_dict(self):
        data = asdict(self)
        data.pop("restaurant", None)
        for key, value in list(data.items()):
            if isinstance(value, Decimal):
                data[key] = float(value)
        return data


def calculate_pricing(cart, coupon=None, user=None, require_available=True):
    """Return a fully resolved :class:`PriceBreakdown` for a cart.

    ``require_available`` adds blocking issues when a food item went out of
    stock after it was added to the cart, or the restaurant closed.
    """
    breakdown = PriceBreakdown()
    items = list(cart.items)

    if not items:
        breakdown.issues.append("Your cart is empty.")
        return breakdown

    restaurant = items[0].food_item.restaurant
    breakdown.restaurant = restaurant

    for item in items:
        food = item.food_item
        breakdown.item_count += item.quantity
        breakdown.mrp_total += food.price * item.quantity
        breakdown.subtotal += food.final_price * item.quantity
        if require_available:
            if not food.is_available:
                breakdown.issues.append(f"{food.name} is currently unavailable. Please remove it to continue.")
            if not restaurant.is_open:
                breakdown.issues.append(f"{restaurant.name} is currently closed for orders.")
            if not restaurant.is_approved or not restaurant.is_active:
                breakdown.issues.append(f"{restaurant.name} is not accepting orders right now.")

    breakdown.mrp_total = money(breakdown.mrp_total)
    breakdown.subtotal = money(breakdown.subtotal)
    breakdown.food_discount = money(breakdown.mrp_total - breakdown.subtotal)

    # Delivery fee: restaurant specific, waived above the configured threshold.
    if breakdown.subtotal >= Decimal(str(settings.FREE_DELIVERY_ABOVE)):
        breakdown.delivery_fee = Decimal("0.00")
    else:
        breakdown.delivery_fee = money(restaurant.delivery_fee)
        breakdown.free_delivery_gap = money(Decimal(str(settings.FREE_DELIVERY_ABOVE)) - breakdown.subtotal)

    breakdown.tax = money(breakdown.subtotal * Decimal(str(settings.TAX_RATE)))
    breakdown.platform_fee = money(settings.PLATFORM_FEE)

    if coupon is not None:
        ok, message = coupon.validate_for(user, breakdown.subtotal, restaurant)
        breakdown.coupon_message = message
        if ok:
            breakdown.coupon_applied = True
            breakdown.coupon_code = coupon.code
            breakdown.coupon_discount = money(coupon.calculate_discount(breakdown.subtotal))
        else:
            breakdown.issues.append(message)

    if breakdown.subtotal < restaurant.minimum_order:
        breakdown.issues.append(
            f"Minimum order for {restaurant.name} is {settings.DEFAULT_CURRENCY}{restaurant.minimum_order:.0f}."
        )

    breakdown.total = money(
        breakdown.subtotal
        - breakdown.coupon_discount
        + breakdown.delivery_fee
        + breakdown.tax
        + breakdown.platform_fee
    )
    if breakdown.total < Decimal("0.00"):
        breakdown.total = Decimal("0.00")
    return breakdown


def resolve_coupon(code, user, subtotal, restaurant=None):
    """Look up a coupon by code and validate it. Returns (coupon|None, message)."""
    from offers.models import Coupon

    code = (code or "").strip().upper()
    if not code:
        return None, "Enter a coupon code."
    try:
        coupon = Coupon.objects.get(code=code)
    except Coupon.DoesNotExist:
        return None, "That coupon code is not valid."
    ok, message = coupon.validate_for(user, subtotal, restaurant)
    return (coupon, message) if ok else (None, message)
