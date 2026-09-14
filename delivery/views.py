"""Delivery partner dashboard, order actions and earnings.

Every query is scoped to ``request.user`` so a partner can never see or touch
another partner's deliveries.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.forms import ProfileForm
from accounts.permissions import delivery_required
from delivery.models import DeliveryAssignment, DeliveryBoyProfile, DeliveryEarning
from orders.models import Order, OrderStatus


def _profile(user):
    profile, _ = DeliveryBoyProfile.objects.get_or_create(user=user)
    return profile


def _my_orders(user):
    return Order.objects.filter(delivery_boy=user).select_related("restaurant", "customer")


@delivery_required
def dashboard(request):
    """Delivery partner dashboard: today's stats, earnings and active jobs."""
    profile = _profile(request.user)
    today = timezone.localdate()
    orders = _my_orders(request.user)

    todays_orders = orders.filter(created_at__date=today)
    completed_today = orders.filter(order_status=OrderStatus.DELIVERED, delivered_at__date=today)
    active = orders.filter(order_status__in=[OrderStatus.ASSIGNED, OrderStatus.PICKED_UP, OrderStatus.OUT_FOR_DELIVERY])

    earnings = request.user.delivery_earnings.all()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    stats = {
        "todays_deliveries": todays_orders.count(),
        "completed_deliveries": orders.filter(order_status=OrderStatus.DELIVERED).count(),
        "pending_deliveries": profile.active_orders,
        "todays_earnings": earnings.filter(created_at__date=today).aggregate(t=Sum("amount"))["t"] or Decimal("0.00"),
        "week_earnings": earnings.filter(created_at__date__gte=week_start).aggregate(t=Sum("amount"))["t"] or Decimal("0.00"),
        "month_earnings": earnings.filter(created_at__date__gte=month_start).aggregate(t=Sum("amount"))["t"] or Decimal("0.00"),
        "total_earnings": earnings.aggregate(t=Sum("amount"))["t"] or Decimal("0.00"),
        "completed_today": completed_today.count(),
        "acceptance_rate": 100 if profile.completed_count else 0,
    }

    context = {
        "profile": profile,
        "stats": stats,
        "active_orders": active.order_by("created_at"),
        "available_orders": _available_orders(profile),
        "recent_completed": orders.filter(order_status=OrderStatus.DELIVERED).order_by("-delivered_at")[:5],
        "notifications": request.user.notifications.filter(is_read=False)[:5],
    }
    return render(request, "delivery/dashboard.html", context)


def _available_orders(profile):
    """Ready-for-pickup orders that this partner can claim."""
    if not profile.is_approved or not profile.is_online:
        return Order.objects.none()
    return Order.objects.filter(
        order_status=OrderStatus.READY_FOR_PICKUP, delivery_boy__isnull=True
    ).select_related("restaurant").order_by("created_at")


@delivery_required
def available_orders(request):
    profile = _profile(request.user)
    orders = _available_orders(profile)
    return render(request, "delivery/available.html", {"profile": profile, "orders": orders})


@delivery_required
def order_detail(request, order_number):
    order = get_object_or_404(_my_orders(request.user).prefetch_related("items"), order_number=order_number)
    return render(
        request,
        "delivery/order_detail.html",
        {"order": order, "profile": _profile(request.user), "assignment": getattr(order, "assignment", None)},
    )


@delivery_required
@require_POST
def claim_order(request, order_number):
    """Self-service claim of an unassigned, ready order."""
    profile = _profile(request.user)
    if not profile.is_approved:
        messages.error(request, "Your partner account is not approved yet.")
        return redirect("delivery:dashboard")
    if not profile.is_online:
        messages.error(request, "Go online to accept deliveries.")
        return redirect("delivery:dashboard")

    from orders.services import assign_delivery_boy

    order = get_object_or_404(Order, order_number=order_number, order_status=OrderStatus.READY_FOR_PICKUP, delivery_boy__isnull=True)
    try:
        assign_delivery_boy(order, request.user, actor=request.user)
        order.refresh_from_db()
        order.assignment.update_status(DeliveryAssignment.Status.ACCEPTED)
        messages.success(request, f"Order #{order.order_number} is yours. Head to {order.restaurant.name}!")
    except ValidationError as exc:
        messages.error(request, exc.messages[0] if exc.messages else "Could not accept this delivery.")
    return redirect("delivery:order_detail", order_number=order.order_number)


@delivery_required
@require_POST
def update_status(request, order_number, status):
    """Delivery partner status transitions with strict ownership checks."""
    order = get_object_or_404(_my_orders(request.user), order_number=order_number)
    assignment = getattr(order, "assignment", None)
    if assignment is None or assignment.delivery_boy_id != request.user.pk:
        return JsonResponse({"ok": False, "message": "This delivery is not assigned to you."}, status=403)

    transitions = {
        "ACCEPTED": (OrderStatus.ASSIGNED, DeliveryAssignment.Status.ACCEPTED),
        "PICKED_UP": (OrderStatus.PICKED_UP, DeliveryAssignment.Status.PICKED_UP),
        "OUT_FOR_DELIVERY": (OrderStatus.OUT_FOR_DELIVERY, DeliveryAssignment.Status.OUT_FOR_DELIVERY),
        "DELIVERED": (OrderStatus.DELIVERED, DeliveryAssignment.Status.DELIVERED),
    }
    if status not in transitions:
        messages.error(request, "Unknown delivery status.")
        return redirect("delivery:order_detail", order_number=order.order_number)

    next_order_status, next_assignment_status = transitions[status]
    if not order.can_transition_to(next_order_status) and order.order_status != next_order_status:
        messages.error(request, f"You cannot mark this order as {status.replace('_', ' ').title()} from {order.status_label}.")
        return redirect("delivery:order_detail", order_number=order.order_number)

    from orders.services import complete_delivery

    if next_order_status == OrderStatus.DELIVERED:
        complete_delivery(order, request.user)
    else:
        order.set_status(next_order_status, note=f"Updated by {request.user.full_name}", actor=request.user)
    assignment.update_status(next_assignment_status)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "status": order.order_status, "label": order.status_label})
    messages.success(request, f"Order #{order.order_number} marked as {order.status_label}.")
    return redirect("delivery:order_detail", order_number=order.order_number)


@delivery_required
@require_POST
def toggle_availability(request):
    profile = _profile(request.user)
    if not profile.is_approved:
        messages.error(request, "Your account must be approved before you can go online.")
        return redirect("delivery:profile")
    profile.set_availability(
        DeliveryBoyProfile.Availability.OFFLINE if profile.is_online else DeliveryBoyProfile.Availability.ONLINE
    )
    messages.success(request, f"You are now {profile.get_availability_status_display().lower()}.")
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "online": profile.is_online})
    return redirect(request.POST.get("next") or "delivery:dashboard")


@delivery_required
def history(request):
    orders = _my_orders(request.user).order_by("-created_at")
    status = request.GET.get("status", "")
    if status:
        orders = orders.filter(order_status=status)
    return render(request, "delivery/history.html", {"orders": orders[:100], "status": status})


@delivery_required
def earnings(request):
    profile = _profile(request.user)
    today = timezone.localdate()
    entries = request.user.delivery_earnings.select_related("order", "order__restaurant").order_by("-created_at")
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    summary = {
        "today": entries.filter(created_at__date=today).aggregate(t=Sum("amount"))["t"] or Decimal("0.00"),
        "week": entries.filter(created_at__date__gte=week_start).aggregate(t=Sum("amount"))["t"] or Decimal("0.00"),
        "month": entries.filter(created_at__date__gte=month_start).aggregate(t=Sum("amount"))["t"] or Decimal("0.00"),
        "total": entries.aggregate(t=Sum("amount"))["t"] or Decimal("0.00"),
        "pending": entries.filter(status=DeliveryEarning.Status.PENDING).aggregate(t=Sum("amount"))["t"] or Decimal("0.00"),
        "settled": entries.filter(status=DeliveryEarning.Status.SETTLED).aggregate(t=Sum("amount"))["t"] or Decimal("0.00"),
        "completed": entries.values("order").distinct().count(),
    }

    # Simple 7 day earnings chart data (real DB values).
    chart = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        total = entries.filter(created_at__date=day).aggregate(t=Sum("amount"))["t"] or Decimal("0.00")
        chart.append({"label": day.strftime("%a"), "value": float(total)})

    return render(request, "delivery/earnings.html", {"profile": profile, "entries": entries[:50], "summary": summary, "chart": chart})


@delivery_required
def profile_view(request):
    profile = _profile(request.user)
    form = ProfileForm(instance=request.user, initial={"first_name": request.user.first_name})

    if request.method == "POST":
        if "update_profile" in request.POST:
            form = ProfileForm(request.POST, request.FILES, instance=request.user)
            if form.is_valid():
                form.save()
                messages.success(request, "Profile updated.")
                return redirect("delivery:profile")
            messages.error(request, "Please correct the errors below.")
        elif "update_vehicle" in request.POST:
            profile.vehicle_type = request.POST.get("vehicle_type", profile.vehicle_type)
            profile.vehicle_number = request.POST.get("vehicle_number", "")
            profile.license_number = request.POST.get("license_number", "")
            profile.current_area = request.POST.get("current_area", "")
            profile.availability_status = request.POST.get("availability_status", profile.availability_status)
            profile.save()
            messages.success(request, "Vehicle details updated.")
            return redirect("delivery:profile")

    stats = {
        "completed": profile.completed_count,
        "active": profile.active_orders,
        "total_earnings": profile.total_earnings,
    }
    return render(request, "delivery/profile.html", {"profile": profile, "form": form, "stats": stats})
