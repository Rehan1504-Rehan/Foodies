"""Request middleware that keeps role scoping tight and cheap to use in views."""

from django.shortcuts import redirect
from django.urls import resolve

from restaurants.models import Restaurant

#: URL names a blocked / mismatched-role user must never be able to reach.
DASHBOARD_PREFIXES = {
    "ADMIN": "/admin-dashboard/",
    "CUSTOMER": "/customer/",
    "RESTAURANT_OWNER": "/restaurant-dashboard/",
    "DELIVERY_BOY": "/delivery/",
}


def _flash_error(request, text):
    """Add an error message without depending on middleware ordering."""
    from django.contrib import messages
    from django.contrib.messages.api import MessageFailure

    try:
        messages.error(request, text)
    except MessageFailure:  # pragma: no cover - safety net only
        pass


class RoleScopeMiddleware:
    """Attach ``request.restaurant`` / ``request.delivery_profile`` for owners
    and partners, and hard-block cross-role dashboard access."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.restaurant = None
        request.delivery_profile = None
        user = getattr(request, "user", None)

        if user is not None and user.is_authenticated:
            if user.role == "RESTAURANT_OWNER":
                request.restaurant = (
                    Restaurant.objects.filter(owner=user).order_by("created_at").first()
                )
            elif user.role == "DELIVERY_BOY":
                from delivery.models import DeliveryBoyProfile

                request.delivery_profile = (
                    DeliveryBoyProfile.objects.filter(user=user).first()
                )

            path = request.path
            for role, prefix in DASHBOARD_PREFIXES.items():
                if path.startswith(prefix) and not (user.role == role or user.is_superuser or user.is_staff):
                    _flash_error(request, "You do not have permission to open that area.")
                    return redirect("dashboard:redirect")

        response = self.get_response(request)
        return response
