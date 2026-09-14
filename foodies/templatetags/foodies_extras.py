"""Small helper filters used across FOODIES templates."""

from decimal import Decimal, InvalidOperation

from django import template
from django.conf import settings

register = template.Library()

STATUS_CLASSES = {
    "PLACED": "fd-badge-placed",
    "CONFIRMED": "fd-badge-confirmed",
    "PREPARING": "fd-badge-preparing",
    "READY_FOR_PICKUP": "fd-badge-ready",
    "ASSIGNED": "fd-badge-assigned",
    "PICKED_UP": "fd-badge-picked",
    "OUT_FOR_DELIVERY": "fd-badge-out",
    "DELIVERED": "fd-badge-delivered",
    "CANCELLED": "fd-badge-cancelled",
    "PENDING": "fd-badge-placed",
    "PAID": "fd-badge-delivered",
    "COD": "fd-badge-confirmed",
    "FAILED": "fd-badge-cancelled",
    "REFUNDED": "fd-badge-assigned",
    "SUCCESS": "fd-badge-delivered",
    "ONLINE": "fd-badge-delivered",
    "OFFLINE": "fd-badge-soft",
    "SETTLED": "fd-badge-delivered",
}


@register.filter
def get_item(mapping, key):
    """Dict lookup by key inside templates: ``{{ cart_qty|get_item:food.pk }}``."""
    if mapping is None:
        return None
    try:
        return mapping.get(key) or mapping.get(str(key))
    except AttributeError:
        return None


@register.filter
def status_class(status):
    return STATUS_CLASSES.get(str(status or "").upper(), "fd-badge-soft")


@register.filter
def inr(value, decimals=2):
    """Format a number as Indian currency."""
    try:
        amount = Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal("0")
    try:
        places = int(decimals)
    except (TypeError, ValueError):
        places = 2
    return f"{settings.DEFAULT_CURRENCY}{amount:,.{places}f}"


@register.filter
def percent_of(value, total):
    try:
        total = float(total or 0)
        if total <= 0:
            return 0
        return max(4, min(100, round(float(value or 0) / total * 100)))
    except (TypeError, ValueError):
        return 0


@register.filter
def star_rating(value):
    try:
        rating = int(round(float(value or 0)))
    except (TypeError, ValueError):
        rating = 0
    rating = max(0, min(5, rating))
    return "★" * rating + "☆" * (5 - rating)


@register.filter
def stars_range(value):
    try:
        return range(1, int(value) + 1)
    except (TypeError, ValueError):
        return range(0)


@register.simple_tag
def query_replace(request, **kwargs):
    """Rebuild the current querystring with overrides (used by filter forms)."""
    params = request.GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    return params.urlencode()


@register.simple_tag
def money(value, decimals=2):
    return inr(value, decimals)
