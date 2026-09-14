"""Coupons / offers with fully server-side validation."""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Coupon(models.Model):
    class DiscountType(models.TextChoices):
        PERCENT = "PERCENT", "Percentage"
        FIXED = "FIXED", "Fixed amount"

    code = models.CharField(max_length=24, unique=True, db_index=True)
    title = models.CharField(max_length=120, blank=True)
    description = models.CharField(max_length=255, blank=True)
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices, default=DiscountType.PERCENT)
    discount_value = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("1"))])
    minimum_order = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    maximum_discount = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("200.00"))
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField()
    usage_limit = models.PositiveIntegerField(default=100, help_text="Total redemptions allowed")
    used_count = models.PositiveIntegerField(default=0)
    per_user_limit = models.PositiveIntegerField(default=1)
    restaurant = models.ForeignKey(
        "restaurants.Restaurant", on_delete=models.CASCADE, null=True, blank=True, related_name="coupons",
        help_text="Leave empty for a platform-wide coupon",
    )
    first_order_only = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.code

    def clean(self):
        if self.valid_until and self.valid_from and self.valid_until <= self.valid_from:
            raise ValidationError({"valid_until": "Valid-until must be after valid-from."})
        if self.discount_type == self.DiscountType.PERCENT and self.discount_value > 100:
            raise ValidationError({"discount_value": "Percentage discount cannot exceed 100%."})

    def save(self, *args, **kwargs):
        self.code = (self.code or "").upper().strip()
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------ rules
    @property
    def is_expired(self):
        return self.valid_until < timezone.now()

    @property
    def is_started(self):
        return self.valid_from <= timezone.now()

    @property
    def is_exhausted(self):
        return self.used_count >= self.usage_limit

    def validate_for(self, user, subtotal, restaurant=None, raise_errors=False):
        """Return (ok, message). Never trust the browser for coupon rules."""
        subtotal = Decimal(str(subtotal or 0))
        reason = None
        if not self.is_active:
            reason = "This coupon is no longer active."
        elif not self.is_started:
            reason = "This coupon is not active yet."
        elif self.is_expired:
            reason = "This coupon has expired."
        elif self.is_exhausted:
            reason = "This coupon has reached its usage limit."
        elif subtotal < self.minimum_order:
            reason = f"Add items worth {settings.DEFAULT_CURRENCY}{self.minimum_order - subtotal:.2f} more to use {self.code}."
        elif self.restaurant_id and restaurant and self.restaurant_id != restaurant.pk:
            reason = "This coupon is only valid on a specific restaurant."
        elif self.first_order_only and user is not None and user.orders.exclude(order_status="CANCELLED").exists():
            reason = "This coupon is valid on your first FOODIES order only."
        elif user is not None and self.per_user_limit and CouponRedemption.objects.filter(coupon=self, user=user).count() >= self.per_user_limit:
            reason = "You have already used this coupon."
        if reason:
            if raise_errors:
                raise ValidationError(reason)
            return False, reason
        return True, "Coupon applied successfully."

    def calculate_discount(self, subtotal):
        subtotal = Decimal(str(subtotal or 0))
        if self.discount_type == self.DiscountType.PERCENT:
            discount = subtotal * self.discount_value / Decimal("100")
        else:
            discount = self.discount_value
        if self.maximum_discount:
            discount = min(discount, self.maximum_discount)
        discount = min(discount, subtotal)
        return discount.quantize(Decimal("0.01"))

    @property
    def display_value(self):
        if self.discount_type == self.DiscountType.PERCENT:
            return f"{self.discount_value:.0f}% OFF"
        return f"₹{self.discount_value:.0f} OFF"


class CouponRedemption(models.Model):
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="redemptions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="coupon_redemptions")
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, null=True, blank=True, related_name="coupon_redemptions")
    discount_amount = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.coupon.code} used by {self.user.email}"
