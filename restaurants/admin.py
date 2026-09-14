from django.contrib import admin
from django.utils.html import format_html

from .models import FavoriteRestaurant, Restaurant


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = (
        "name", "owner", "city", "primary_cuisine", "rating", "delivery_time",
        "delivery_fee", "is_open", "is_approved", "is_active", "created_at",
    )
    list_filter = ("is_approved", "is_open", "is_active", "city", "created_at")
    search_fields = ("name", "owner__email", "city", "area", "cuisine_type", "phone")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("owner",)
    readonly_fields = ("rating", "rating_count", "created_at", "updated_at", "logo_preview", "cover_preview")
    date_hierarchy = "created_at"
    list_per_page = 20
    actions = ["approve_restaurants", "reject_restaurants"]
    fieldsets = (
        ("Ownership", {"fields": ("owner", "name", "slug", "description")}),
        ("Branding", {"fields": ("logo", "logo_preview", "cover_image", "cover_preview")}),
        ("Contact & address", {"fields": ("phone", "email", "address", "area", "city", "state", "pincode")}),
        ("Service details", {"fields": ("cuisine_type", "delivery_time", "delivery_fee", "minimum_order")}),
        ("Status", {"fields": ("is_open", "is_approved", "is_active", "rejection_reason", "rating", "rating_count")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Logo")
    def logo_preview(self, obj):
        if obj.logo:
            return format_html('<img src="{}" style="height:60px;border-radius:8px" />', obj.logo.url)
        return "—"

    @admin.display(description="Cover")
    def cover_preview(self, obj):
        if obj.cover_image:
            return format_html('<img src="{}" style="height:60px;border-radius:8px" />', obj.cover_image.url)
        return "—"

    @admin.action(description="Approve selected restaurants")
    def approve_restaurants(self, request, queryset):
        updated = queryset.update(is_approved=True, is_active=True, rejection_reason="")
        self.message_user(request, f"{updated} restaurant(s) approved and now visible to customers.")

    @admin.action(description="Reject selected restaurants")
    def reject_restaurants(self, request, queryset):
        updated = queryset.update(is_approved=False)
        self.message_user(request, f"{updated} restaurant(s) rejected.")


@admin.register(FavoriteRestaurant)
class FavoriteRestaurantAdmin(admin.ModelAdmin):
    list_display = ("user", "restaurant", "created_at")
    search_fields = ("user__email", "restaurant__name")
    autocomplete_fields = ("user", "restaurant")
