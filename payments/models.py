"""Payment records for FOODIES orders (COD, Razorpay, mock gateway)."""

from decimal import Decimal

from django.db import models


class Payment(models.Model):
    class Method(models.TextChoices):
        COD = "COD", "Cash on Delivery"
        RAZORPAY = "RAZORPAY", "Razorpay"
        MOCK = "MOCK", "Mock / Test Gateway"
        UPI = "UPI", "UPI"
        CARD = "CARD", "Card"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"
        REFUNDED = "REFUNDED", "Refunded"

    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="payments")
    payment_id = models.CharField(max_length=120, unique=True, db_index=True)
    gateway_order_id = models.CharField(max_length=120, blank=True)
    gateway_signature = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    payment_method = models.CharField(max_length=12, choices=Method.choices, default=Method.COD)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    gateway_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["order", "status"])]

    def __str__(self):
        return f"{self.payment_id} — {self.payment_method} ({self.status})"

    @property
    def is_successful(self):
        return self.status == self.Status.SUCCESS
