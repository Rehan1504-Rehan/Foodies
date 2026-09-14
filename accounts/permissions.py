"""Role based access control for FOODIES.

One decorator per role plus a couple of convenience mixins. Every dashboard,
API endpoint and view that touches private data is protected with these so a
customer can never reach restaurant/admin screens and vice versa.
"""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

try:  # DRF is optional at import time (not needed by the plain views)
    from rest_framework.permissions import BasePermission
except Exception:  # pragma: no cover - DRF is a hard dependency in practice
    BasePermission = object


class HasRole(BasePermission):
    """DRF permission that only lets the listed roles through (superusers bypass).

    Wrong-role requests get a clean ``403`` instead of an empty ``200``.
    """

    allowed_roles = ()

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        roles = getattr(view, "allowed_roles", None) or self.allowed_roles
        return user.role in roles


class IsCustomer(HasRole):
    allowed_roles = ("CUSTOMER",)


class IsRestaurantOwner(HasRole):
    allowed_roles = ("RESTAURANT_OWNER",)


class IsDeliveryBoy(HasRole):
    allowed_roles = ("DELIVERY_BOY",)


class IsAdminRole(HasRole):
    allowed_roles = ("ADMIN",)


ROLE_HOME = {
    "ADMIN": "dashboard:admin_home",
    "CUSTOMER": "dashboard:customer_home",
    "RESTAURANT_OWNER": "dashboard:restaurant_home",
    "DELIVERY_BOY": "dashboard:delivery_home",
}


def home_url_for(user):
    """Where a user should land after login."""
    if not user.is_authenticated:
        return "core:home"
    if user.is_superuser or user.role == "ADMIN":
        return "dashboard:admin_home"
    return ROLE_HOME.get(user.role, "core:home")


def role_required(*roles, allow_superuser=True):
    """Allow only the given roles (superusers optionally bypass)."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                messages.info(request, "Please log in to continue.")
                return redirect_to_login(request.get_full_path())
            if allow_superuser and user.is_superuser:
                return view_func(request, *args, **kwargs)
            if user.role not in roles:
                raise PermissionDenied(
                    "Your FOODIES account does not have access to this area."
                )
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


customer_required = role_required("CUSTOMER")
restaurant_required = role_required("RESTAURANT_OWNER")
delivery_required = role_required("DELIVERY_BOY")
admin_required = role_required("ADMIN")


def verified_restaurant_required(view_func):
    """Restaurant owner view that also guarantees an owned restaurant exists."""

    @wraps(view_func)
    @restaurant_required
    def _wrapped(request, *args, **kwargs):
        if not request.restaurant:
            messages.warning(request, "Create your restaurant profile first.")
            return redirect("dashboard:restaurant_restaurant_create")
        return view_func(request, *args, **kwargs)

    return _wrapped


class RoleRequiredMixin:
    """Class based view mixin mirroring :func:`role_required`."""

    allowed_roles = ()

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if user.is_superuser or user.role in self.allowed_roles:
            return super().dispatch(request, *args, **kwargs)
        raise PermissionDenied("Your FOODIES account does not have access to this area.")


class CustomerMixin(RoleRequiredMixin):
    allowed_roles = ("CUSTOMER",)


class RestaurantOwnerMixin(RoleRequiredMixin):
    allowed_roles = ("RESTAURANT_OWNER",)


class DeliveryBoyMixin(RoleRequiredMixin):
    allowed_roles = ("DELIVERY_BOY",)


class AdminRoleMixin(RoleRequiredMixin):
    allowed_roles = ("ADMIN",)
