"""Payment API (/api/payments/...)."""

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from orders.models import Order
from payments.models import Payment
from payments.serializers import PaymentSerializer
from payments.services import create_razorpay_order, razorpay_enabled, verify_razorpay_signature


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_list(request):
    """The requesting user only ever sees their own payments."""
    user = request.user
    if user.is_superuser or user.role == "ADMIN":
        queryset = Payment.objects.all()
    elif user.role == "RESTAURANT_OWNER":
        queryset = Payment.objects.filter(order__restaurant__owner=user)
    else:
        queryset = Payment.objects.filter(order__customer=user)
    return Response(PaymentSerializer(queryset.select_related("order")[:100], many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_detail(request, payment_id):
    payment = Payment.objects.filter(payment_id=payment_id).select_related("order").first()
    if payment is None:
        return Response({"detail": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)
    user = request.user
    owns = (
        payment.order.customer_id == user.pk
        or payment.order.restaurant.owner_id == user.pk
        or user.is_superuser
        or user.role == "ADMIN"
    )
    if not owns:
        return Response({"detail": "Not your payment."}, status=status.HTTP_403_FORBIDDEN)
    return Response(PaymentSerializer(payment).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_order_payment(request, order_number):
    """Create (or refresh) a gateway order for a pending FOODIES order."""
    order = Order.objects.filter(order_number=order_number, customer=request.user).first()
    if order is None:
        return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)
    if order.payment_status in {"PAID", "COD"}:
        return Response({"detail": "This order does not require an online payment."}, status=status.HTTP_400_BAD_REQUEST)

    if razorpay_enabled():
        data, error = create_razorpay_order(order)
        if error:
            return Response({"detail": error}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"gateway": "razorpay", **data})

    return Response(
        {
            "gateway": "mock",
            "message": "Razorpay keys are not configured — FOODIES is using the built-in test gateway.",
            "amount": float(order.total_amount),
            "currency": "INR",
            "test_mode": True,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def confirm_payment(request):
    """Verify a gateway payment before marking it successful."""
    from payments.services import mark_payment_failed, mark_payment_success, mock_pay

    order_number = request.data.get("order_number")
    order = Order.objects.filter(order_number=order_number, customer=request.user).first()
    if order is None:
        return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)
    payment = order.payments.filter(status=Payment.Status.PENDING).order_by("-created_at").first()
    if payment is None:
        return Response({"detail": "No pending payment for this order."}, status=status.HTTP_400_BAD_REQUEST)

    if request.data.get("gateway") == "mock" or not razorpay_enabled():
        mock_pay(payment, simulate_failure=bool(request.data.get("simulate_failure")))
    else:
        razorpay_payment_id = request.data.get("razorpay_payment_id", "")
        razorpay_order_id = request.data.get("razorpay_order_id", "")
        signature = request.data.get("razorpay_signature", "")
        if not verify_razorpay_signature(razorpay_order_id, razorpay_payment_id, signature):
            mark_payment_failed(payment, reason="Invalid signature")
            return Response({"detail": "Payment signature verification failed."}, status=status.HTTP_400_BAD_REQUEST)
        mark_payment_success(payment, gateway_id=razorpay_payment_id, signature=signature)

    payment.refresh_from_db()
    order.refresh_from_db()
    return Response(
        {
            "message": "Payment processed.",
            "payment": PaymentSerializer(payment).data,
            "order_status": order.order_status,
            "payment_status": order.payment_status,
            "gateway": "razorpay" if razorpay_enabled() else "mock",
        }
    )


@api_view(["GET"])
def payment_config(request):
    """Expose only the publishable key id — never the secret."""
    return Response(
        {
            "gateway": "razorpay" if razorpay_enabled() else "mock",
            "razorpay_key_id": settings.RAZORPAY_KEY_ID if razorpay_enabled() else "",
            "currency": "INR",
        }
    )
