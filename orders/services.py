"""Order domain services: notifications, checkout, cancellation, assignment."""

import logging
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from cart.services import calculate_pricing, money
from delivery.models import DeliveryAssignment, DeliveryBoyProfile, DeliveryEarning
from menu.models import FoodItem
from offers.models import Coupon, CouponRedemption
from orders.models import Notification, Order, OrderItem, OrderStatus, PaymentStatus

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Notifications
# --------------------------------------------------------------------------- #
def notify(user, title, message="", kind=Notification.Kind.ORDER, url="", order=None):
    if user is None:
        return None
    return Notification.objects.create(
        recipient=user, title=title, message=message, kind=kind, url=url, order=order
    )


STATUS_MESSAGES = {
    OrderStatus.PLACED: ("Order placed successfully", "We have sent your order to {restaurant}."),
    OrderStatus.CONFIRMED: ("Order confirmed 🎉", "{restaurant} accepted your order and will start cooking soon."),
    OrderStatus.PREPARING: ("Your food is being prepared 👨‍🍳", "{restaurant} has started preparing your order."),
    OrderStatus.READY_FOR_PICKUP: ("Food is ready 📦", "Your order is packed and waiting for a delivery partner."),
    OrderStatus.ASSIGNED: ("Delivery partner assigned 🛵", "{partner} will pick up your order shortly."),
    OrderStatus.PICKED_UP: ("Order picked up", "Your food has been picked up from {restaurant}."),
    OrderStatus.OUT_FOR_DELIVERY: ("Out for delivery 🚀", "Your order is on the way. Please keep your phone handy."),
    OrderStatus.DELIVERED: ("Order delivered ✅", "Enjoy your meal! Don't forget to rate {restaurant}."),
    OrderStatus.CANCELLED: ("Order cancelled", "Your order #{order} has been cancelled."),
}


def _format(text, order):
    return text.format(
        restaurant=order.restaurant.name,
        partner=order.delivery_partner_name or "A delivery partner",
        order=order.order_number,
    )


def notify_order_status(order, status, note=""):
    """Fan out a status change to customer, restaurant, delivery partner and admin."""
    status = OrderStatus(status)
    title_template, body_template = STATUS_MESSAGES.get(status, (f"Order {status.label}", ""))
    title, body = _format(title_template, order), _format(body_template, order)
    if note:
        body = f"{body} {note}".strip()

    notify(order.customer, title, body, Notification.Kind.ORDER, order.get_absolute_url(), order)

    if status in {OrderStatus.PLACED, OrderStatus.CANCELLED}:
        notify(
            order.restaurant.owner,
            "New order received 🔔" if status == OrderStatus.PLACED else "Order cancelled",
            f"#{order.order_number} • {order.items_total_quantity} items • {settings.DEFAULT_CURRENCY}{order.total_amount}",
            Notification.Kind.RESTAURANT,
            "/restaurant-dashboard/orders/",
            order,
        )
    elif status == OrderStatus.CANCELLED and order.delivery_boy:
        pass

    if order.delivery_boy:
        partner_titles = {
            OrderStatus.ASSIGNED: ("New delivery assigned 🛵", "Pick up from {restaurant} and deliver to the customer."),
            OrderStatus.CANCELLED: ("Delivery cancelled", "Order #{order} was cancelled."),
            OrderStatus.DELIVERED: ("Delivery completed 💰", "Earnings added to your wallet."),
        }
        if status in partner_titles:
            p_title, p_body = partner_titles[status]
            notify(
                order.delivery_boy,
                _format(p_title, order),
                _format(p_body, order),
                Notification.Kind.DELIVERY,
                f"/delivery/orders/{order.order_number}/",
                order,
            )

    if status == OrderStatus.PLACED:
        for admin in _admin_users():
            notify(admin, f"New order #{order.order_number}", f"{order.restaurant.name} • {settings.DEFAULT_CURRENCY}{order.total_amount}", Notification.Kind.ORDER, "/admin-dashboard/orders/", order)
    if status == OrderStatus.READY_FOR_PICKUP:
        for admin in _admin_users():
            notify(admin, f"Order #{order.order_number} ready for pickup", "Assign a delivery partner.", Notification.Kind.DELIVERY, "/admin-dashboard/delivery/", order)


def _admin_users():
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.filter(role="ADMIN", is_active=True)[:5]


# --------------------------------------------------------------------------- #
# Checkout
# --------------------------------------------------------------------------- #
@transaction.atomic
def create_order_from_cart(user, address, coupon_code="", payment_method="COD", special_instructions=""):
    """Turn a cart into an immutable order (single atomic transaction).

    Steps: validate cart → validate availability → price server side →
    create order → create items → create payment → coupon redemption →
    clear cart. Any failure rolls the whole thing back.
    """
    from cart.models import Cart
    from payments.models import Payment
    from payments.services import create_payment_record

    cart = Cart.objects.select_for_update().filter(user=user).first()
    if cart is None or not cart.cart_items.exists():
        raise ValidationError("Your cart is empty.")

    if address is None or address.user_id != user.pk:
        raise ValidationError("Please select a valid delivery address.")

    locked_items = list(cart.cart_items.select_related("food_item", "food_item__restaurant").select_for_update())

    # Re-check availability from the database (never from the request).
    food_ids = [item.food_item_id for item in locked_items]
    fresh_items = {f.pk: f for f in FoodItem.objects.filter(pk__in=food_ids)}
    for item in locked_items:
        food = fresh_items.get(item.food_item_id)
        if food is None or not food.is_available:
            raise ValidationError(f"'{item.food_item.name}' is no longer available. Please update your cart.")

    restaurant = locked_items[0].food_item.restaurant
    if not restaurant.is_approved or not restaurant.is_active:
        raise ValidationError("This restaurant is not accepting orders right now.")
    if not restaurant.is_open:
        raise ValidationError("This restaurant is currently closed.")

    coupon = None
    if coupon_code:
        coupon = Coupon.objects.select_for_update().filter(code=coupon_code.strip().upper()).first()
        if coupon is None:
            raise ValidationError("That coupon code is not valid.")

    pricing = calculate_pricing(cart, coupon=coupon, user=user)
    if pricing.issues:
        raise ValidationError(pricing.issues)
    if coupon and not pricing.coupon_applied:
        raise ValidationError(pricing.coupon_message or "Coupon could not be applied.")

    order = Order.objects.create(
        customer=user,
        restaurant=restaurant,
        delivery_address=address,
        delivery_address_text=address.full_address,
        customer_name=address.full_name,
        customer_phone=address.phone,
        subtotal=pricing.subtotal,
        discount=pricing.food_discount,
        delivery_fee=pricing.delivery_fee,
        tax=pricing.tax,
        platform_fee=pricing.platform_fee,
        coupon=coupon,
        coupon_discount=pricing.coupon_discount,
        total_amount=pricing.total,
        special_instructions=special_instructions[:255],
        estimated_delivery_time=restaurant.delivery_time,
        order_status=OrderStatus.PLACED,
        payment_status=PaymentStatus.COD if payment_method == "COD" else PaymentStatus.PENDING,
    )

    order_items = []
    for cart_item in locked_items:
        food = fresh_items[cart_item.food_item_id]
        order_items.append(
            OrderItem(
                order=order,
                food_item=food,
                food_name=food.name,
                category_name=food.category.name,
                is_veg=food.is_veg,
                price=food.final_price,
                mrp=food.price,
                quantity=cart_item.quantity,
                total=food.final_price * cart_item.quantity,
            )
        )
    OrderItem.objects.bulk_create(order_items)

    # Keep popularity counters in sync for "Popular Food" sections.
    for cart_item in locked_items:
        FoodItem.objects.filter(pk=cart_item.food_item_id).update(order_count=models_f_plus(cart_item.quantity))

    if coupon:
        Coupon.objects.filter(pk=coupon.pk).update(used_count=coupon.used_count + 1)
        CouponRedemption.objects.create(coupon=coupon, user=user, order=order, discount_amount=pricing.coupon_discount)

    create_payment_record(order, payment_method=payment_method)
    order.set_status(OrderStatus.PLACED, note="Order placed by customer")

    cart.clear()
    logger.info("Order %s created for %s (%s)", order.order_number, user.email, order.total_amount)
    return order


def models_f_plus(quantity):
    from django.db.models import F

    return F("order_count") + quantity


@transaction.atomic
def cancel_order(order, actor=None, reason="Cancelled by customer"):
    """Cancel an order, restoring coupon usage and recording the reason."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if not order.is_cancellable:
        raise ValidationError("This order can no longer be cancelled. Please contact support.")

    order.cancellation_reason = reason[:255]
    order.save(update_fields=["cancellation_reason"])
    order.set_status(OrderStatus.CANCELLED, note=reason, actor=actor)

    if order.coupon_id:
        Coupon.objects.filter(pk=order.coupon_id).update(used_count=max(0, order.coupon.used_count - 1))
        if order.payment_status == PaymentStatus.PAID:
            order.payment_status = PaymentStatus.REFUNDED
            order.save(update_fields=["payment_status"])

    if hasattr(order, "assignment"):
        order.assignment.update_status(DeliveryAssignment.Status.CANCELLED)
        DeliveryEarning.objects.filter(assignment=order.assignment).delete()
    return order


@transaction.atomic
def assign_delivery_boy(order, delivery_boy, actor=None):
    """Assign (or re-assign) an approved delivery partner to a ready order."""
    from django.contrib.auth import get_user_model

    order = Order.objects.select_for_update().get(pk=order.pk)
    if not delivery_boy or delivery_boy.role != "DELIVERY_BOY":
        raise ValidationError("Please choose a valid delivery partner.")
    if not delivery_boy.is_active:
        raise ValidationError("This delivery partner account is inactive.")
    if order.order_status not in {OrderStatus.READY_FOR_PICKUP, OrderStatus.PLACED, OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.ASSIGNED}:
        raise ValidationError(f"Order #{order.order_number} can not be assigned in status {order.status_label}.")

    profile, _ = DeliveryBoyProfile.objects.get_or_create(user=delivery_boy)
    if not profile.is_approved:
        raise ValidationError("This delivery partner is not approved yet.")

    if hasattr(order, "assignment"):
        previous = order.assignment
        if previous.delivery_boy_id == delivery_boy.pk:
            raise ValidationError("This order is already assigned to that partner.")
        DeliveryEarning.objects.filter(assignment=previous).delete()
        previous.delete()

    assignment = DeliveryAssignment.objects.create(
        order=order,
        delivery_boy=delivery_boy,
        assigned_by=actor,
        earning_amount=profile.earning_per_delivery,
    )
    order.delivery_boy = delivery_boy
    order.save(update_fields=["delivery_boy", "updated_at"])
    order.set_status(OrderStatus.ASSIGNED, note=f"Assigned to {delivery_boy.full_name}", actor=actor)

    DeliveryEarning.objects.create(
        delivery_boy=delivery_boy,
        order=order,
        assignment=assignment,
        amount=profile.earning_per_delivery,
    )
    return assignment


def complete_delivery(order, actor):
    """Called when a partner marks an order delivered."""
    order.set_status(OrderStatus.DELIVERED, note=f"Delivered by {actor.full_name}", actor=actor)
    if order.payment_status == PaymentStatus.COD:
        pass  # COD collected on delivery; status already COD.
    elif order.payment_status == PaymentStatus.PENDING:
        order.payment_status = PaymentStatus.PAID
        order.save(update_fields=["payment_status"])
    return order


def todays_order_stats(restaurant=None, delivery_boy=None):
    today = timezone.localdate()
    qs = Order.objects.filter(created_at__date=today)
    if restaurant:
        qs = qs.filter(restaurant=restaurant)
    if delivery_boy:
        qs = qs.filter(delivery_boy=delivery_boy)
    return {
        "count": qs.count(),
        "revenue": money(sum((o.total_amount for o in qs.filter(order_status=OrderStatus.DELIVERED)), Decimal("0"))),
        "pending": qs.exclude(order_status__in=[OrderStatus.DELIVERED, OrderStatus.CANCELLED]).count(),
    }
