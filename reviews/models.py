"""Customer reviews — only verified, delivered orders can be reviewed."""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Review(models.Model):
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    restaurant = models.ForeignKey("restaurants.Restaurant", on_delete=models.CASCADE, related_name="reviews")
    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="review")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(max_length=1000, blank=True)
    reply = models.TextField(max_length=600, blank=True, help_text="Restaurant owner reply")
    is_hidden = models.BooleanField(default=False, help_text="Hidden by admin moderation")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("customer", "order")

    def __str__(self):
        return f"{self.rating}★ by {self.customer.full_name} for {self.restaurant.name}"

    @property
    def stars(self):
        return "★" * self.rating + "☆" * (5 - self.rating)

    def save(self, *args, **kwargs):
        if self.order_id:
            self.restaurant_id = self.order.restaurant_id
        super().save(*args, **kwargs)
        self.restaurant.recalculate_rating()
