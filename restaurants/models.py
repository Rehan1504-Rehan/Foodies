"""Restaurant domain models."""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Avg, Count
from django.urls import reverse
from django.utils.text import slugify


class RestaurantQuerySet(models.QuerySet):
    def approved(self):
        return self.filter(is_approved=True, is_active=True)

    def open_now(self):
        return self.approved().filter(is_open=True)

    def with_rating(self):
        return self.annotate(avg_rating=Avg("reviews__rating"), review_count=Count("reviews", distinct=True))


class Restaurant(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="restaurants",
        limit_choices_to={"role": "RESTAURANT_OWNER"},
    )
    name = models.CharField(max_length=140)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to="restaurants/logos/", blank=True, null=True)
    cover_image = models.ImageField(upload_to="restaurants/covers/", blank=True, null=True)
    phone = models.CharField(max_length=15)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255)
    area = models.CharField(max_length=120)
    city = models.CharField(max_length=80, db_index=True)
    state = models.CharField(max_length=80, blank=True)
    pincode = models.CharField(max_length=10, blank=True)
    cuisine_type = models.CharField(max_length=200, help_text="Comma separated, e.g. North Indian, Chinese")
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal("0.00"))
    rating_count = models.PositiveIntegerField(default=0)
    delivery_time = models.PositiveIntegerField(default=30, help_text="Average delivery time in minutes")
    delivery_fee = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("29.00"))
    minimum_order = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("99.00"), validators=[MinValueValidator(Decimal("0"))]
    )
    is_open = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    rejection_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = RestaurantQuerySet.as_manager()

    class Meta:
        ordering = ["-rating", "name"]
        indexes = [models.Index(fields=["city", "is_approved", "is_open"])]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:150] or "restaurant"
            slug, counter = base, 1
            while Restaurant.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                counter += 1
                slug = f"{base}-{counter}"
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("restaurants:detail", args=[self.slug])

    @property
    def cuisines(self):
        return [c.strip() for c in (self.cuisine_type or "").split(",") if c.strip()]

    @property
    def primary_cuisine(self):
        return self.cuisines[0] if self.cuisines else "Multi-cuisine"

    @property
    def rating_stars(self):
        return int(round(float(self.rating)))

    @property
    def is_new(self):
        return self.rating_count == 0

    def recalculate_rating(self, save=True):
        """Recompute the aggregate rating from real customer reviews."""
        stats = self.reviews.filter(is_hidden=False).aggregate(avg=Avg("rating"), count=Count("id"))
        self.rating = Decimal(str(round(stats["avg"] or 0, 2)))
        self.rating_count = stats["count"] or 0
        if save:
            Restaurant.objects.filter(pk=self.pk).update(rating=self.rating, rating_count=self.rating_count)
        return self.rating

    def item_count(self):
        return self.food_items.filter(is_available=True).count()


class FavoriteRestaurant(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorite_restaurants")
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "restaurant")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} ❤ {self.restaurant}"
