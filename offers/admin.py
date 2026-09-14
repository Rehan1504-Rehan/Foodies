from django.contrib import admin

from .models import Coupon, CouponRedemption


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        "code", "display_value", "minimum_order", "maximum_discount", "valid_until",
        "usage_limit", "used_count", "restaurant", "is_active",
    )
    list_filter = ("discount_type", "is_active", "first_order_only", "valid_until", "restaurant")
    search_fields = ("code", "title", "description")
    autocomplete_fields = ("restaurant",)
    list_editable = ("is_active",)
    date_hierarchy = "valid_until"
    actions = ["activate_coupons", "deactivate_coupons"]

    @admin.action(description="Activate selected coupons")
    def activate_coupons(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=True)} coupon(s) activated.")

    @admin.action(description="Deactivate selected coupons")
    def deactivate_coupons(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=False)} coupon(s) deactivated.")


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    list_display = ("coupon", "user", "order", "discount_amount", "created_at")
    list_filter = ("created_at", "coupon")
    search_fields = ("coupon__code", "user__email", "order__order_number")
    autocomplete_fields = ("coupon", "user", "order")
