"""Order lifecycle models: Order, OrderItem, status history and notifications."""

import random
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class OrderStatus(models.TextChoices):
    PLACED = "PLACED", "Order Placed"
    CONFIRMED = "CONFIRMED", "Restaurant Confirmed"
    PREPARING = "PREPARING", "Food Preparing"
    READY_FOR_PICKUP = "READY_FOR_PICKUP", "Ready for Pickup"
    ASSIGNED = "ASSIGNED", "Delivery Boy Assigned"
    PICKED_UP = "PICKED_UP", "Picked Up"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY", "Out for Delivery"
    DELIVERED = "DELIVERED", "Delivered"
    CANCELLED = "CANCELLED", "Cancelled"


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PAID = "PAID", "Paid"
    COD = "COD", "Cash on Delivery"
    FAILED = "FAILED", "Failed"
    REFUNDED = "REFUNDED", "Refunded"


#: Ordered happy-path pipeline used by the tracking page.
ORDER_FLOW = [
    OrderStatus.PLACED,
    OrderStatus.CONFIRMED,
    OrderStatus.PREPARING,
    OrderStatus.READY_FOR_PICKUP,
    OrderStatus.ASSIGNED,
    OrderStatus.PICKED_UP,
    OrderStatus.OUT_FOR_DELIVERY,
    OrderStatus.DELIVERED,
]

#: Allowed transitions — enforced server side for every role.
ALLOWED_TRANSITIONS = {
    OrderStatus.PLACED: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
    OrderStatus.PREPARING: {OrderStatus.READY_FOR_PICKUP, OrderStatus.CANCELLED},
    OrderStatus.READY_FOR_PICKUP: {OrderStatus.ASSIGNED, OrderStatus.CANCELLED},
    OrderStatus.ASSIGNED: {OrderStatus.PICKED_UP, OrderStatus.CANCELLED},
    OrderStatus.PICKED_UP: {OrderStatus.OUT_FOR_DELIVERY},
    OrderStatus.OUT_FOR_DELIVERY: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}


def generate_order_number():
    while True:
        number = f"FD{random.randint(10000, 99999)}{random.randint(10, 99)}"
        if not Order.objects.filter(order_number=number).exists():
            return number


class Order(models.Model):
    order_number = models.CharField(max_length=20, unique=True, blank=True, db_index=True)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    restaurant = models.ForeignKey("restaurants.Restaurant", on_delete=models.PROTECT, related_name="orders")
    delivery_boy = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deliveries",
        limit_choices_to={"role": "DELIVERY_BOY"},
    )
    delivery_address = models.ForeignKey(
        "accounts.Address", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    # Snapshot of the address at order time — history must never change.
    delivery_address_text = models.TextField()
    customer_name = models.CharField(max_length=120)
    customer_phone = models.CharField(max_length=15)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    platform_fee = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    coupon = models.ForeignKey("offers.Coupon", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    coupon_discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    payment_status = models.CharField(max_length=12, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    order_status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PLACED, db_index=True)
    special_instructions = models.CharField(max_length=255, blank=True)
    estimated_delivery_time = models.PositiveIntegerField(default=35, help_text="Minutes")
    cancellation_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["customer", "order_status"]), models.Index(fields=["restaurant", "order_status"])]

    def __str__(self):
        return f"#{self.order_number} — {self.restaurant.name}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = generate_order_number()
        super().save(*args, **kwargs)

    # ------------------------------------------------------------- properties
    def get_absolute_url(self):
        return reverse("orders:detail", args=[self.order_number])

    @property
    def status_label(self):
        return OrderStatus(self.order_status).label

    @property
    def is_active(self):
        return self.order_status not in {OrderStatus.DELIVERED, OrderStatus.CANCELLED}

    @property
    def is_cancellable(self):
        """Customers may cancel until the food is ready / picked up."""
        return self.order_status in {
            OrderStatus.PLACED,
            OrderStatus.CONFIRMED,
            OrderStatus.PREPARING,
            OrderStatus.READY_FOR_PICKUP,
        }

    @property
    def is_delivered(self):
        return self.order_status == OrderStatus.DELIVERED

    @property
    def can_review(self):
        return self.is_delivered and not hasattr(self, "review")

    @property
    def items_total_quantity(self):
        return int(self.items.aggregate(t=models.Sum("quantity"))["t"] or 0)

    @property
    def savings(self):
        return (self.discount or Decimal("0")) + (self.coupon_discount or Decimal("0"))

    @property
    def restaurant_earning(self):
        from django.conf import settings as dj_settings

        return round(self.subtotal * Decimal(str(1 - dj_settings.RESTAURANT_COMMISSION_RATE)), 2)

    @property
    def progress_percent(self):
        if self.order_status == OrderStatus.CANCELLED:
            return 100
        try:
            index = ORDER_FLOW.index(OrderStatus(self.order_status))
        except ValueError:
            index = 0
        return int(round((index + 1) / len(ORDER_FLOW) * 100))

    @property
    def tracking_steps(self):
        """``[(label, state, history_entry|None), ...]`` for the visual tracker.

        Always returns 3-tuples so templates and the tracking API can unpack
        them safely, including for cancelled orders.
        """
        history = {h.status: h for h in self.status_history.all()}

        if self.order_status == OrderStatus.CANCELLED:
            return [
                (OrderStatus.PLACED.label, "done", history.get(OrderStatus.PLACED)),
                (OrderStatus.CANCELLED.label, "cancelled", history.get(OrderStatus.CANCELLED)),
            ]

        current_index = ORDER_FLOW.index(OrderStatus(self.order_status))
        steps = []
        for index, status in enumerate(ORDER_FLOW):
            if index == current_index:
                state = "current"
            elif index < current_index or status in history:
                state = "done"
            else:
                state = "todo"
            steps.append((OrderStatus(status).label, state, history.get(status)))
        return steps

    def can_transition_to(self, new_status):
        if new_status == self.order_status:
            return False
        if new_status == OrderStatus.CANCELLED:
            return self.is_cancellable
        return new_status in ALLOWED_TRANSITIONS.get(OrderStatus(self.order_status), set())

    # ---------------------------------------------------------------- actions
    def set_status(self, new_status, note="", actor=None, notify=True):
        """Update the order status, write history and fan out notifications."""
        new_status = OrderStatus(new_status)
        self.order_status = new_status
        if new_status == OrderStatus.DELIVERED:
            self.delivered_at = timezone.now()
        if new_status == OrderStatus.CANCELLED:
            self.cancelled_at = timezone.now()
        self.save(update_fields=["order_status", "delivered_at", "cancelled_at", "updated_at"])
        self.status_history.create(status=new_status, note=note, created_by=actor)
        if notify:
            self.notify_status_change(new_status, note)
        return self

    def notify_status_change(self, status, note=""):
        from orders.services import notify_order_status

        notify_order_status(self, status, note)

    def mark_paid(self, method="RAZORPAY"):
        self.payment_status = PaymentStatus.COD if method == "COD" else PaymentStatus.PAID
        self.save(update_fields=["payment_status", "updated_at"])

    @property
    def delivery_partner_name(self):
        return self.delivery_boy.full_name if self.delivery_boy else None


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    food_item = models.ForeignKey("menu.FoodItem", on_delete=models.SET_NULL, null=True, blank=True, related_name="order_items")
    food_name = models.CharField(max_length=140)
    category_name = models.CharField(max_length=80, blank=True)
    is_veg = models.BooleanField(default=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, help_text="Unit price actually charged")
    mrp = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    quantity = models.PositiveIntegerField(default=1)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.quantity} x {self.food_name}"

    def save(self, *args, **kwargs):
        self.total = (self.price or Decimal("0")) * self.quantity
        super().save(*args, **kwargs)

    @property
    def line_total(self):
        return self.price * self.quantity


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_history")
    status = models.CharField(max_length=20, choices=OrderStatus.choices)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name_plural = "Order status history"

    def __str__(self):
        return f"#{self.order.order_number} → {self.status}"


class Notification(models.Model):
    """Database backed notification inbox for all four roles."""

    class Kind(models.TextChoices):
        ORDER = "ORDER", "Order"
        PAYMENT = "PAYMENT", "Payment"
        RESTAURANT = "RESTAURANT", "Restaurant"
        DELIVERY = "DELIVERY", "Delivery"
        ACCOUNT = "ACCOUNT", "Account"
        OFFER = "OFFER", "Offer"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=140)
    message = models.CharField(max_length=400, blank=True)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.ORDER)
    url = models.CharField(max_length=255, blank=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.recipient.email}: {self.title}"

    def mark_read(self):
        if not self.is_read:
            Notification.objects.filter(pk=self.pk).update(is_read=True)
