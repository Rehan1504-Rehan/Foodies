"""Authentication, profile and address management for all FOODIES roles."""

from django.contrib import messages
from django.contrib.auth import get_user_model, login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.forms import (
    AddressForm,
    AdminAuthenticationForm,
    CustomerRegisterForm,
    DeliveryRegisterForm,
    FoodieAuthenticationForm,
    ProfileForm,
    RestaurantOwnerRegisterForm,
)
from accounts.permissions import customer_required
from orders.models import Notification
from orders.services import notify

User = get_user_model()


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
class FoodieLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = FoodieAuthenticationForm
    redirect_authenticated_user = True

    def get_success_url(self):
        from accounts.permissions import home_url_for

        return reverse(home_url_for(self.request.user))

    def form_invalid(self, form):
        messages.error(self.request, "Incorrect email or password. Please try again.")
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["show_demo_accounts"] = True
        return context


class FoodieLogoutView(LogoutView):
    next_page = "core:home"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            messages.success(request, "You have been logged out. See you soon!")
        return super().dispatch(request, *args, **kwargs)


@transaction.atomic
def register(request, role="customer"):
    """Single registration entry point for customers, owners and partners."""
    role = (role or "customer").lower()
    config = {
        "customer": (CustomerRegisterForm, "CUSTOMER", "dashboard:customer_home", "Customer"),
        "restaurant": (RestaurantOwnerRegisterForm, "RESTAURANT_OWNER", "dashboard:restaurant_home", "Restaurant Owner"),
        "delivery": (DeliveryRegisterForm, "DELIVERY_BOY", "delivery:dashboard", "Delivery Partner"),
    }
    if role not in config:
        messages.error(request, "Unknown account type.")
        return redirect("core:home")

    form_class, user_role, redirect_name, label = config[role]

    if request.method == "POST":
        form = form_class(request.POST, request.FILES)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = user_role
            user.save()

            if user_role == "RESTAURANT_OWNER":
                from restaurants.models import Restaurant

                Restaurant.objects.create(
                    owner=user,
                    name=form.cleaned_data.get("restaurant_name") or f"{user.full_name}'s Kitchen",
                    cuisine_type="Multi-cuisine",
                    city=form.cleaned_data.get("city") or "Ahmedabad",
                    area=form.cleaned_data.get("city") or "Ahmedabad",
                    address="Add your full address from the dashboard",
                    phone=user.phone,
                    email=user.email,
                    is_open=False,
                    is_approved=False,
                )
                for admin in User.objects.filter(role="ADMIN", is_active=True):
                    notify(
                        admin,
                        "New restaurant registration 🏪",
                        f"{user.full_name} registered a restaurant and needs approval.",
                        Notification.Kind.RESTAURANT,
                        "/admin-dashboard/approvals/",
                    )
            elif user_role == "DELIVERY_BOY":
                from delivery.models import DeliveryBoyProfile

                DeliveryBoyProfile.objects.create(
                    user=user,
                    vehicle_type=form.cleaned_data.get("vehicle_type", "BIKE"),
                    vehicle_number=form.cleaned_data.get("vehicle_number", ""),
                    license_number=form.cleaned_data.get("license_number", ""),
                    is_approved=False,
                )
                for admin in User.objects.filter(role="ADMIN", is_active=True):
                    notify(
                        admin,
                        "New delivery partner 🛵",
                        f"{user.full_name} signed up and is waiting for approval.",
                        Notification.Kind.DELIVERY,
                        "/admin-dashboard/delivery-boys/",
                    )

            login(request, user)
            messages.success(request, f"Welcome to FOODIES, {user.short_name}! Your {label} account is ready.")
            if user_role == "RESTAURANT_OWNER":
                messages.info(request, "Complete your restaurant profile — it goes live once our team approves it.")
            if user_role == "DELIVERY_BOY":
                messages.info(request, "Your partner account is pending approval. You can browse the dashboard meanwhile.")
            return redirect(redirect_name)
        messages.error(request, "Please fix the highlighted errors below.")
    else:
        form = form_class()

    return render(
        request,
        "registration/register.html",
        {"form": form, "role": role, "role_label": config[role][3]},
    )


# --------------------------------------------------------------------------- #
# Profile
# --------------------------------------------------------------------------- #
@login_required
def profile(request):
    """Role-aware profile page (customer / restaurant / delivery / admin)."""
    template = {
        "CUSTOMER": "customer/profile.html",
        "RESTAURANT_OWNER": "restaurant/profile.html",
        "DELIVERY_BOY": "delivery/profile.html",
        "ADMIN": "admin_console/profile.html",
    }.get(request.user.role, "customer/profile.html")
    if request.user.is_superuser and request.user.role != "ADMIN":
        template = "admin_console/profile.html"

    form = ProfileForm(instance=request.user)
    password_form = PasswordChangeForm(request.user)

    if request.method == "POST":
        if "update_profile" in request.POST:
            form = ProfileForm(request.POST, request.FILES, instance=request.user)
            if form.is_valid():
                form.save()
                messages.success(request, "Profile updated successfully.")
                return redirect("accounts:profile")
            messages.error(request, "Could not update your profile. Please check the form.")
        elif "change_password" in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                messages.success(request, "Password changed successfully.")
                return redirect("accounts:profile")
            messages.error(request, "Password could not be changed. Please review the errors.")

    context = {"form": form, "password_form": password_form, "addresses": request.user.addresses.all()}
    return render(request, template, context)


@customer_required
def address_list(request):
    addresses = request.user.addresses.all()
    return render(request, "customer/addresses.html", {"addresses": addresses, "form": AddressForm()})


@customer_required
def address_create(request):
    if request.method == "POST":
        form = AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            address.save()
            messages.success(request, "Address saved.")
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"ok": True, "id": address.pk, "label": str(address)})
            return redirect(request.POST.get("next") or "accounts:addresses")
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        messages.error(request, "Please correct the address form.")
    else:
        form = AddressForm(initial={"full_name": request.user.full_name, "phone": request.user.phone})
    return render(request, "customer/address_form.html", {"form": form})


@customer_required
def address_edit(request, pk):
    address = get_object_or_404(request.user.addresses, pk=pk)
    if request.method == "POST":
        form = AddressForm(request.POST, instance=address)
        if form.is_valid():
            form.save()
            messages.success(request, "Address updated.")
            return redirect("accounts:addresses")
        messages.error(request, "Please correct the address form.")
    else:
        form = AddressForm(instance=address)
    return render(request, "customer/address_form.html", {"form": form, "address": address})


@customer_required
@require_POST
def address_delete(request, pk):
    address = get_object_or_404(request.user.addresses, pk=pk)
    address.delete()
    messages.success(request, "Address removed.")
    return redirect("accounts:addresses")


@customer_required
@require_POST
def address_set_default(request, pk):
    address = get_object_or_404(request.user.addresses, pk=pk)
    address.is_default = True
    address.save()
    messages.success(request, "Default delivery address updated.")
    return redirect("accounts:addresses")


@login_required
def notifications(request):
    """Database backed notification centre shared by every role."""
    queryset = request.user.notifications.select_related("order")
    unread_only = request.GET.get("filter") == "unread"
    if unread_only:
        queryset = queryset.filter(is_read=False)
    if request.GET.get("mark_read") == "1":
        request.user.notifications.filter(is_read=False).update(is_read=True)
        messages.success(request, "All notifications marked as read.")
        return redirect("accounts:notifications")
    return render(
        request,
        "customer/notifications.html",
        {"notifications": queryset[:100], "unread_only": unread_only, "unread_count": request.user.notifications.filter(is_read=False).count()},
    )


@login_required
@require_POST
def notification_read(request, pk):
    notification = get_object_or_404(request.user.notifications, pk=pk)
    notification.mark_read()
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    return redirect(notification.url or "accounts:notifications")
