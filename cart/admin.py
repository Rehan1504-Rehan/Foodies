"""Django admin registrations for saved carts (support & debugging)."""

from django.contrib import admin

from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    autocomplete_fields = ("food_item",)
    fields = ("cart", "food_item", "quantity", "added_at")
    readonly_fields = ("added_at",)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "total_items", "restaurant", "updated_at")
    list_filter = ("updated_at",)
    search_fields = ("user__email", "user__first_name", "user__last_name", "cart_items__food_item__name")
    list_select_related = ("user",)
    inlines = (CartItemInline,)
    list_per_page = 30
    date_hierarchy = "updated_at"

    @admin.display(description="Items")
    def total_items(self, obj):
        return obj.total_items

    @admin.display(description="Restaurant")
    def restaurant(self, obj):
        restaurant = obj.restaurant
        return restaurant.name if restaurant else "—"


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("id", "cart", "food_item", "quantity", "amount", "added_at")
    list_filter = ("added_at",)
    search_fields = ("cart__user__email", "food_item__name")
    autocomplete_fields = ("cart", "food_item")
    list_select_related = ("cart", "food_item")
    list_per_page = 40

    @admin.display(description="Amount")
    def amount(self, obj):
        return obj.line_total
