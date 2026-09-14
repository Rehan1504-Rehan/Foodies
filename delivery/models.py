"""Delivery partner profile, assignments and earnings."""

from decimal import Decimal

from datetime import date, datetime, time

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone


def _as_aware(value, boundary):
    """Normalise a date/datetime into a timezone-aware datetime."""
    if isinstance(value, datetime):
        return value if timezone.is_aware(value) else timezone.make_aware(value)
    if isinstance(value, date):
        return timezone.make_aware(datetime.combine(value, boundary))
    return value


class DeliveryBoyProfile(models.Model):
    class VehicleType(models.TextChoices):
        BIKE = "BIKE", "Bike"
        SCOOTER = "SCOOTER", "Scooter"
        BICYCLE = "BICYCLE", "Bicycle"
        EV = "EV", "Electric Vehicle"

    class Availability(models.TextChoices):
        ONLINE = "ONLINE", "Online"
        OFFLINE = "OFFLINE", "Offline"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="delivery_profile")
    vehicle_type = models.CharField(max_length=12, choices=VehicleType.choices, default=VehicleType.BIKE)
    vehicle_number = models.CharField(max_length=20, blank=True)
    license_number = models.CharField(max_length=30, blank=True)
    current_area = models.CharField(max_length=120, blank=True)
    availability_status = models.CharField(max_length=10, choices=Availability.choices, default=Availability.OFFLINE, db_index=True)
    is_approved = models.BooleanField(default=False)
    earning_per_delivery = models.DecimalField(
        max_digits=7, decimal_places=2, default=Decimal(str(settings.DEFAULT_DELIVERY_EARNING))
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.full_name} ({self.get_vehicle_type_display()})"

    @property
    def is_online(self):
        return self.availability_status == self.Availability.ONLINE

    @property
    def active_orders(self):
        return self.user.deliveries.filter(order_status__in=["ASSIGNED", "PICKED_UP", "OUT_FOR_DELIVERY"]).count()

    @property
    def completed_count(self):
        return self.user.deliveries.filter(order_status="DELIVERED").count()

    def earnings_for(self, start=None, end=None):
        """Sum earnings between two moments (timezone aware, accepts dates)."""
        qs = self.user.delivery_earnings.all()
        if start is not None:
            qs = qs.filter(created_at__gte=_as_aware(start, time.min))
        if end is not None:
            qs = qs.filter(created_at__lte=_as_aware(end, time.max))
        return qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    @property
    def today_earnings(self):
        today = timezone.localdate()
        return self.earnings_for(start=today, end=timezone.now())

    @property
    def total_earnings(self):
        return self.earnings_for()

    def set_availability(self, status):
        self.availability_status = status
        self.save(update_fields=["availability_status", "updated_at"])
        return self


class DeliveryAssignment(models.Model):
    """One record per order/delivery-partner pairing, including its timeline."""

    class Status(models.TextChoices):
        ASSIGNED = "ASSIGNED", "Assigned"
        ACCEPTED = "ACCEPTED", "Accepted by Partner"
        PICKED_UP = "PICKED_UP", "Picked Up"
        OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY", "Out for Delivery"
        DELIVERED = "DELIVERED", "Delivered"
        CANCELLED = "CANCELLED", "Cancelled"
        REJECTED = "REJECTED", "Rejected"

    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="assignment")
    delivery_boy = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assignments")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assignments_made"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ASSIGNED, db_index=True)
    distance_km = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("3.50"))
    earning_amount = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("40.00"))
    notes = models.CharField(max_length=255, blank=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    out_for_delivery_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-assigned_at"]

    def __str__(self):
        return f"{self.order.order_number} → {self.delivery_boy.full_name}"

    def update_status(self, status):
        self.status = status
        now = timezone.now()
        stamp_field = {
            self.Status.ACCEPTED: "accepted_at",
            self.Status.PICKED_UP: "picked_up_at",
            self.Status.OUT_FOR_DELIVERY: "out_for_delivery_at",
            self.Status.DELIVERED: "delivered_at",
        }.get(status)
        if stamp_field and not getattr(self, stamp_field):
            setattr(self, stamp_field, now)
        self.save()
        return self


class DeliveryEarning(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SETTLED = "SETTLED", "Settled"

    delivery_boy = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="delivery_earnings")
    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="earnings")
    assignment = models.ForeignKey(DeliveryAssignment, on_delete=models.SET_NULL, null=True, blank=True, related_name="earnings")
    amount = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("40.00"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    settled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["delivery_boy", "created_at"])]

    def __str__(self):
        return f"{self.delivery_boy.full_name} +{self.amount}"
