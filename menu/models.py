"""Menu / food catalogue models."""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Count, Q, Sum
from django.utils.text import slugify


class Category(models.Model):
    """Top level food category (Pizza, Biryani, Thali ...)."""

    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    description = models.CharField(max_length=255, blank=True)
    image = models.ImageField(upload_to="categories/", blank=True, null=True)
    icon = models.CharField(max_length=10, blank=True, help_text="Emoji used when no image is uploaded")
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("menu:category", args=[self.slug])

    @property
    def emoji(self):
        return self.icon or "🍽️"

    def available_items(self):
        return FoodItem.objects.filter(category=self, is_available=True, restaurant__is_approved=True, restaurant__is_active=True)


class FoodItemQuerySet(models.QuerySet):
    def available(self):
        return self.filter(is_available=True, restaurant__is_approved=True, restaurant__is_active=True)

    def veg(self):
        return self.filter(is_veg=True)

    def non_veg(self):
        return self.filter(is_veg=False)


class FoodItem(models.Model):
    restaurant = models.ForeignKey("restaurants.Restaurant", on_delete=models.CASCADE, related_name="food_items")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="food_items")
    name = models.CharField(max_length=140)
    slug = models.SlugField(max_length=170, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("1.00"))]
    )
    discount_price = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))]
    )
    image = models.ImageField(upload_to="food/", blank=True, null=True)
    is_veg = models.BooleanField(default=True)
    is_available = models.BooleanField(default=True)
    is_recommended = models.BooleanField(default=False, help_text="Featured on the FOODIES home page")
    preparation_time = models.PositiveIntegerField(default=15, help_text="Minutes")
    order_count = models.PositiveIntegerField(default=0, help_text="How many times this item was ordered")
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = FoodItemQuerySet.as_manager()

    class Meta:
        ordering = ["category__display_order", "name"]
        indexes = [models.Index(fields=["restaurant", "is_available"])]

    def __str__(self):
        return f"{self.name} — {self.restaurant.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:140] or "item"
            slug = base
            counter = 1
            while FoodItem.objects.filter(restaurant=self.restaurant, slug=slug).exclude(pk=self.pk).exists():
                counter += 1
                slug = f"{base}-{counter}"
            self.slug = slug
        if self.discount_price is not None and self.discount_price >= self.price:
            # A "discount" that is not cheaper than the base price is meaningless.
            self.discount_price = None
        super().save(*args, **kwargs)

    @property
    def final_price(self):
        """The price the customer actually pays — always resolved server side."""
        if self.discount_price is not None and self.discount_price > 0:
            return self.discount_price
        return self.price

    @property
    def discount_amount(self):
        if self.discount_price is not None and self.discount_price > 0:
            return self.price - self.discount_price
        return Decimal("0.00")

    @property
    def discount_percent(self):
        if self.price and self.discount_amount:
            return int(round(float(self.discount_amount) / float(self.price) * 100))
        return 0

    @property
    def has_discount(self):
        return self.discount_amount > 0

    @property
    def food_type(self):
        return "Veg" if self.is_veg else "Non-Veg"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("restaurants:detail", args=[self.restaurant.slug]) + f"#item-{self.pk}"


class FavoriteFoodItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorite_food_items")
    food_item = models.ForeignKey(FoodItem, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "food_item")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} ❤ {self.food_item}"
