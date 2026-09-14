"""Checkout + payment flow.

Checkout is a single atomic transaction (see ``orders.services.create_order_from_cart``)
so an interrupted payment can never leave a broken order behind.
"""

import logging

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.forms import AddressForm
from accounts.permissions import customer_required
from cart.models import Cart
from cart.services import calculate_pricing
from offers.models import Coupon
from orders.models import Order, OrderStatus, PaymentStatus
from orders.services import create_order_from_cart
from payments.models import Payment
from payments.services import (
    create_razorpay_order,
    mark_payment_failed,
    mark_payment_success,
    mock_pay,
    razorpay_enabled,
    verify_razorpay_signature,
)

logger = logging.getLogger(__name__)


def _cart_with_coupon(request):
    cart = Cart.objects.filter(user=request.user).first()
    coupon = None
    coupon_id = request.session.get("coupon_id")
    if coupon_id:
        coupon = Coupon.objects.filter(pk=coupon_id, is_active=True).first()
        if coupon and not coupon.validate_for(request.user, cart.subtotal if cart else 0)[0]:
            coupon = None
            request.session.pop("coupon_id", None)
    return cart, coupon


@customer_required
def checkout(request):
    """Cart → address → coupon → summary → payment method."""
    cart, coupon = _cart_with_coupon(request)
    if cart is None or cart.is_empty:
        messages.warning(request, "Your cart is empty — add something delicious first!")
        return redirect("restaurants:list")

    pricing = calculate_pricing(cart, coupon=coupon, user=request.user)
    addresses = request.user.addresses.all()
    default_address = addresses.filter(is_default=True).first() or addresses.first()

    if request.method == "POST":
        address_id = request.POST.get("address_id") or (default_address.pk if default_address else None)
        address = request.user.addresses.filter(pk=address_id).first() if address_id else None
        if address is None:
            messages.error(request, "Please select a delivery address.")
            return redirect("payments:checkout")

        payment_method = (request.POST.get("payment_method") or "COD").upper()
        if payment_method not in {"COD", "RAZORPAY", "MOCK", "UPI"}:
            payment_method = "COD"
        if payment_method in {"RAZORPAY", "UPI"} and not razorpay_enabled():
            payment_method = "MOCK"

        try:
            order = create_order_from_cart(
                user=request.user,
                address=address,
                coupon_code=coupon.code if coupon else "",
                payment_method=payment_method,
                special_instructions=request.POST.get("special_instructions", ""),
            )
        except ValidationError as exc:
            for message in (exc.messages or ["Checkout failed. Please review your cart."]):
                messages.error(request, message)
            return redirect("cart:detail")

        request.session.pop("coupon_id", None)

        if order.payment_status == PaymentStatus.COD:
            messages.success(request, f"Order #{order.order_number} placed! Pay {settings.DEFAULT_CURRENCY}{order.total_amount} on delivery.")
            return redirect("orders:detail", order_number=order.order_number)

        return redirect("payments:pay", order_number=order.order_number)

    if pricing.issues:
        for issue in pricing.issues:
            messages.warning(request, issue)

    context = {
        "cart": cart,
        "pricing": pricing,
        "addresses": addresses,
        "default_address": default_address,
        "address_form": AddressForm(initial={"full_name": request.user.full_name, "phone": request.user.phone}),
        "razorpay_enabled": razorpay_enabled(),
        "coupon": coupon if pricing.coupon_applied else None,
    }
    return render(request, "customer/checkout.html", context)


@customer_required
def pay(request, order_number):
    """Payment page for a pending online payment."""
    order = get_object_or_404(Order.objects.select_related("restaurant"), order_number=order_number, customer=request.user)
    if order.order_status == OrderStatus.CANCELLED:
        messages.error(request, "This order was cancelled.")
        return redirect("orders:detail", order_number=order.order_number)
    if order.payment_status == PaymentStatus.PAID:
        messages.info(request, "This order is already paid.")
        return redirect("orders:detail", order_number=order.order_number)

    payment = order.payments.filter(status=Payment.Status.PENDING).order_by("-created_at").first()
    razorpay_data, gateway_error = (None, "")
    if razorpay_enabled():
        razorpay_data, gateway_error = create_razorpay_order(order)
        if gateway_error:
            messages.warning(request, gateway_error)

    context = {
        "order": order,
        "payment": payment,
        "razorpay_enabled": razorpay_enabled(),
        "razorpay_data": razorpay_data,
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
        "gateway_error": gateway_error,
        "mock_mode": not razorpay_enabled(),
    }
    return render(request, "customer/payment.html", context)


@customer_required
@require_POST
def payment_mock(request, order_number):
    """Local test gateway: settle or fail a payment instantly."""
    order = get_object_or_404(Order, order_number=order_number, customer=request.user)
    payment = order.payments.filter(status=Payment.Status.PENDING).order_by("-created_at").first()
    if payment is None:
        messages.info(request, "No pending payment for this order.")
        return redirect("orders:detail", order_number=order.order_number)

    simulate_failure = request.POST.get("simulate") == "failure"
    mock_pay(payment, simulate_failure=simulate_failure)
    if simulate_failure:
        messages.error(request, "Test gateway reported a failure. You can retry or switch to cash on delivery.")
        return redirect("payments:pay", order_number=order.order_number)

    order.refresh_from_db()
    messages.success(request, f"Payment of {settings.DEFAULT_CURRENCY}{payment.amount} successful. Order #{order.order_number} confirmed!")
    return redirect("orders:detail", order_number=order.order_number)


@customer_required
@require_POST
def payment_razorpay_callback(request, order_number):
    """Verify the Razorpay signature before trusting a payment."""
    order = get_object_or_404(Order, order_number=order_number, customer=request.user)
    payment = order.payments.filter(status=Payment.Status.PENDING).order_by("-created_at").first()
    razorpay_payment_id = request.POST.get("razorpay_payment_id", "")
    razorpay_order_id = request.POST.get("razorpay_order_id", "")
    signature = request.POST.get("razorpay_signature", "")

    if payment is None:
        messages.warning(request, "No pending payment found for this order.")
        return redirect("orders:detail", order_number=order.order_number)

    if verify_razorpay_signature(razorpay_order_id, razorpay_payment_id, signature):
        mark_payment_success(
            payment,
            gateway_id=razorpay_payment_id,
            signature=signature,
            response={"razorpay_order_id": razorpay_order_id, "razorpay_payment_id": razorpay_payment_id, "verified": True},
        )
        messages.success(request, "Payment verified. Your food is on its way!")
    else:
        mark_payment_failed(payment, reason="Signature verification failed")
        messages.error(request, "We could not verify that payment. Please try again.")
    return redirect("orders:detail", order_number=order.order_number)


@customer_required
def payment_history(request):
    payments = (
        Payment.objects.filter(order__customer=request.user)
        .select_related("order", "order__restaurant")
        .order_by("-created_at")
    )
    total_paid = sum((p.amount for p in payments if p.status == Payment.Status.SUCCESS), start=0)
    return render(request, "customer/payments.html", {"payments": payments, "total_paid": total_paid})


@require_POST
def razorpay_webhook(request):
    """Optional webhook endpoint — signature verified when a secret is set."""
    import hashlib
    import hmac
    import json

    secret = settings.RAZORPAY_KEY_SECRET
    body = request.body
    if secret:
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, request.headers.get("X-Razorpay-Signature", "")):
            return JsonResponse({"ok": False, "message": "Invalid signature"}, status=400)
    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        return JsonResponse({"ok": False, "message": "Invalid payload"}, status=400)
    logger.info("Razorpay webhook received: %s", payload.get("event"))
    return JsonResponse({"ok": True})
