from django.contrib import admin
from django.utils.html import format_html

from .models import Category, FavoriteFoodItem, FoodItem


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "emoji", "display_order", "is_active", "item_count", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    list_editable = ("display_order", "is_active")
    list_per_page = 30

    @admin.display(description="Items")
    def item_count(self, obj):
        return obj.food_items.count()


@admin.register(FoodItem)
class FoodItemAdmin(admin.ModelAdmin):
    list_display = (
        "name", "restaurant", "category", "price", "discount_price", "food_type_badge",
        "is_available", "is_recommended", "order_count", "updated_at",
    )
    list_filter = ("is_veg", "is_available", "is_recommended", "category", "restaurant")
    search_fields = ("name", "description", "restaurant__name")
    autocomplete_fields = ("restaurant",)
    readonly_fields = ("order_count", "created_at", "updated_at", "image_preview")
    date_hierarchy = "created_at"
    list_per_page = 25
    list_select_related = ("restaurant", "category")
    fieldsets = (
        ("Item", {"fields": ("restaurant", "category", "name", "slug", "description")}),
        ("Pricing", {"fields": ("price", "discount_price")}),
        ("Media", {"fields": ("image", "image_preview")}),
        ("Availability", {"fields": ("is_veg", "is_available", "is_recommended", "preparation_time")}),
        ("Stats", {"fields": ("order_count", "rating", "created_at", "updated_at")}),
    )

    @admin.display(description="Type")
    def food_type_badge(self, obj):
        colour = "#16a34a" if obj.is_veg else "#dc2626"
        return format_html('<span style="color:{};font-weight:600">{}</span>', colour, obj.food_type)

    @admin.display(description="Preview")
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="height:70px;border-radius:8px" />', obj.image.url)
        return "—"


@admin.register(FavoriteFoodItem)
class FavoriteFoodItemAdmin(admin.ModelAdmin):
    list_display = ("user", "food_item", "created_at")
    search_fields = ("user__email", "food_item__name")
    autocomplete_fields = ("user", "food_item")
