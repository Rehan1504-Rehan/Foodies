"""Payment gateway layer.

* ``COD``  — cash on delivery, nothing to charge online.
* ``RAZORPAY`` — online payment via the Razorpay Orders API. Credentials come
  from environment variables only (never hard-coded, never exposed to the
  browser except the public key id).
* ``MOCK`` — a fully working local test gateway used when no Razorpay keys are
  configured, so the whole order flow can be exercised offline.
"""

import base64
import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.request
import uuid
from decimal import Decimal

from django.conf import settings

from payments.models import Payment

logger = logging.getLogger(__name__)

RAZORPAY_API = "https://api.razorpay.com/v1"


def payment_id_for(order, method):
    return f"pay_{method.lower()}_{order.order_number.lower()}_{uuid.uuid4().hex[:8]}"


def create_payment_record(order, payment_method="COD"):
    """Create the Payment row that mirrors an order (called inside checkout)."""
    method = (payment_method or "COD").upper()
    if method not in dict(Payment.Method.choices):
        method = "COD"
    status = Payment.Status.SUCCESS if method == Payment.Method.COD else Payment.Status.PENDING
    payment = Payment.objects.create(
        order=order,
        payment_id=payment_id_for(order, method),
        amount=order.total_amount,
        payment_method=method,
        status=status,
        gateway_response={"mode": "cash_on_delivery"} if method == "COD" else {},
    )
    return payment


def mark_payment_success(payment, gateway_id="", signature="", response=None):
    payment.status = Payment.Status.SUCCESS
    if gateway_id:
        payment.payment_id = gateway_id
    payment.gateway_signature = signature
    payment.gateway_response = response or payment.gateway_response
    payment.save()
    order = payment.order
    from orders.models import PaymentStatus

    order.payment_status = (
        PaymentStatus.COD if payment.payment_method == Payment.Method.COD else PaymentStatus.PAID
    )
    order.save(update_fields=["payment_status", "updated_at"])
    return payment


def mark_payment_failed(payment, response=None, reason=""):
    payment.status = Payment.Status.FAILED
    payment.gateway_response = response or {"error": reason or "Payment failed"}
    payment.save()
    order = payment.order
    from orders.models import PaymentStatus

    order.payment_status = PaymentStatus.FAILED
    order.save(update_fields=["payment_status", "updated_at"])
    return payment


# --------------------------------------------------------------------------- #
# Razorpay
# --------------------------------------------------------------------------- #
def razorpay_enabled():
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET) and not settings.PAYMENTS_MOCK_MODE


def _razorpay_request(path, payload=None, method="POST"):
    url = f"{RAZORPAY_API}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    token = base64.b64encode(f"{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}".encode()).decode()
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Basic {token}")
    request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=15) as response:  # nosec - fixed host, https only
        return json.loads(response.read().decode())


def create_razorpay_order(order):
    """Create a Razorpay order and persist its id on the Payment row."""
    payment = order.payments.filter(status=Payment.Status.PENDING).order_by("-created_at").first()
    if payment is None:
        payment = create_payment_record(order, Payment.Method.RAZORPAY)
    amount_paise = int(Decimal(order.total_amount) * 100)
    try:
        gateway_order = _razorpay_request(
            "/orders",
            {
                "amount": amount_paise,
                "currency": "INR",
                "receipt": order.order_number,
                "notes": {"order_number": order.order_number, "customer": order.customer.email},
            },
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        logger.warning("Razorpay order creation failed for %s: %s", order.order_number, exc)
        return None, "Unable to reach the payment gateway. Please try cash on delivery or retry."

    payment.payment_method = Payment.Method.RAZORPAY
    payment.gateway_order_id = gateway_order.get("id", "")
    payment.gateway_response = {"razorpay_order": gateway_order}
    payment.save()
    return {
        "key_id": settings.RAZORPAY_KEY_ID,
        "razorpay_order_id": payment.gateway_order_id,
        "amount": amount_paise,
        "currency": "INR",
        "description": f"FOODIES order #{order.order_number}",
        "name": settings.SITE_NAME,
        "prefill": {"name": order.customer_name, "contact": order.customer_phone, "email": order.customer.email},
    }, ""


def verify_razorpay_signature(razorpay_order_id, razorpay_payment_id, signature):
    """Verify the checkout callback signature (HMAC-SHA256 with the key secret)."""
    if not settings.RAZORPAY_KEY_SECRET:
        return False
    message = f"{razorpay_order_id}|{razorpay_payment_id}".encode()
    expected = hmac.new(settings.RAZORPAY_KEY_SECRET.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


# --------------------------------------------------------------------------- #
# Mock gateway (local development / demos)
# --------------------------------------------------------------------------- #
def mock_pay(payment, simulate_failure=False):
    """Instantly settle a payment to emulate a real gateway round trip."""
    if simulate_failure:
        return mark_payment_failed(payment, {"mode": "mock", "reason": "Simulated failure"})
    return mark_payment_success(
        payment,
        gateway_id=f"mockpay_{uuid.uuid4().hex[:14]}",
        signature="mock-signature",
        response={"mode": "mock", "status": "captured", "amount": float(payment.amount)},
    )
