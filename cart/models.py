"""Database backed shopping cart."""

from decimal import Decimal

from django.conf import settings
from django.db import models

from menu.models import FoodItem


class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart<{self.user.email}>"

    # ---------------------------------------------------------------- helpers
    @property
    def items(self):
        return self.cart_items.select_related("food_item", "food_item__restaurant", "food_item__category")

    @property
    def total_items(self):
        return int(self.cart_items.aggregate(total=models.Sum("quantity"))["total"] or 0)

    @property
    def restaurant(self):
        """A FOODIES cart always belongs to a single restaurant."""
        item = self.cart_items.select_related("food_item__restaurant").first()
        return item.food_item.restaurant if item else None

    @property
    def is_empty(self):
        return not self.cart_items.exists()

    @property
    def mrp_total(self):
        """Sum of base prices (before item level discounts)."""
        return sum((item.food_item.price * item.quantity for item in self.items), Decimal("0.00"))

    @property
    def subtotal(self):
        """Sum of discounted item prices."""
        return sum((item.food_item.final_price * item.quantity for item in self.items), Decimal("0.00"))

    @property
    def food_discount(self):
        return self.mrp_total - self.subtotal

    def quantity_of(self, food_item):
        item = self.cart_items.filter(food_item=food_item).first()
        return item.quantity if item else 0

    def add_item(self, food_item: FoodItem, quantity: int = 1):
        """Add an item, replacing the cart if it belongs to another restaurant."""
        current = self.restaurant
        if current and current.pk != food_item.restaurant_id:
            self.cart_items.all().delete()
        item, created = CartItem.objects.get_or_create(cart=self, food_item=food_item, defaults={"quantity": 0})
        item.quantity = max(0, item.quantity + quantity)
        if item.quantity == 0:
            item.delete()
        else:
            item.save()
        self.save(update_fields=["updated_at"])
        return item

    def set_quantity(self, food_item: FoodItem, quantity: int):
        item = self.cart_items.filter(food_item=food_item).first()
        if quantity <= 0:
            if item:
                item.delete()
            return None
        if item is None:
            return self.add_item(food_item, quantity)
        item.quantity = quantity
        item.save(update_fields=["quantity"])
        self.save(update_fields=["updated_at"])
        return item

    def clear(self):
        self.cart_items.all().delete()
        self.save(update_fields=["updated_at"])

    def remove_item(self, food_item: FoodItem):
        self.cart_items.filter(food_item=food_item).delete()


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="cart_items")
    food_item = models.ForeignKey(FoodItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("cart", "food_item")
        ordering = ["added_at"]

    def __str__(self):
        return f"{self.quantity} x {self.food_item.name}"

    @property
    def unit_price(self):
        return self.food_item.final_price

    @property
    def line_total(self):
        return self.food_item.final_price * self.quantity

    @property
    def line_mrp(self):
        return self.food_item.price * self.quantity

    @property
    def savings(self):
        return self.line_mrp - self.line_total
