from django.contrib import admin
from django.utils.html import format_html

from .models import Notification, Order, OrderItem, OrderStatus, OrderStatusHistory


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("food_name", "category_name", "price", "mrp", "quantity", "total")
    can_delete = False


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ("status", "note", "created_by", "created_at")
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number", "customer", "restaurant", "delivery_boy", "total_amount",
        "payment_status", "order_status_badge", "created_at",
    )
    list_filter = ("order_status", "payment_status", "created_at", "restaurant")
    search_fields = ("order_number", "customer__email", "customer_name", "customer_phone", "restaurant__name")
    autocomplete_fields = ("customer", "restaurant", "delivery_boy", "coupon", "delivery_address")
    readonly_fields = (
        "order_number", "subtotal", "discount", "delivery_fee", "tax", "platform_fee",
        "coupon_discount", "total_amount", "created_at", "updated_at", "delivered_at", "cancelled_at",
    )
    inlines = [OrderItemInline, OrderStatusHistoryInline]
    date_hierarchy = "created_at"
    list_per_page = 25
    list_select_related = ("customer", "restaurant", "delivery_boy")
    actions = ["mark_confirmed", "mark_delivered", "mark_cancelled"]
    fieldsets = (
        ("Order", {"fields": ("order_number", "customer", "restaurant", "delivery_boy", "order_status", "payment_status")}),
        ("Delivery", {"fields": ("delivery_address", "delivery_address_text", "customer_name", "customer_phone", "estimated_delivery_time", "special_instructions")}),
        ("Money (server calculated)", {"fields": ("subtotal", "discount", "delivery_fee", "tax", "platform_fee", "coupon", "coupon_discount", "total_amount")}),
        ("Timestamps", {"fields": ("created_at", "updated_at", "delivered_at", "cancelled_at", "cancellation_reason")}),
    )

    @admin.display(description="Status")
    def order_status_badge(self, obj):
        palette = {
            OrderStatus.PLACED: "#f59e0b",
            OrderStatus.CONFIRMED: "#3b82f6",
            OrderStatus.PREPARING: "#8b5cf6",
            OrderStatus.READY_FOR_PICKUP: "#0ea5e9",
            OrderStatus.ASSIGNED: "#6366f1",
            OrderStatus.PICKED_UP: "#14b8a6",
            OrderStatus.OUT_FOR_DELIVERY: "#f97316",
            OrderStatus.DELIVERED: "#16a34a",
            OrderStatus.CANCELLED: "#dc2626",
        }
        colour = palette.get(obj.order_status, "#64748b")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:999px;font-size:11px">{}</span>',
            colour,
            obj.status_label,
        )

    @admin.action(description="Mark selected orders as confirmed")
    def mark_confirmed(self, request, queryset):
        for order in queryset.filter(order_status=OrderStatus.PLACED):
            order.set_status(OrderStatus.CONFIRMED, note="Confirmed by admin", actor=request.user)
        self.message_user(request, "Selected orders confirmed.")

    @admin.action(description="Mark selected orders as delivered")
    def mark_delivered(self, request, queryset):
        count = 0
        for order in queryset.exclude(order_status=OrderStatus.DELIVERED):
            order.set_status(OrderStatus.DELIVERED, note="Marked delivered by admin", actor=request.user)
            count += 1
        self.message_user(request, f"{count} order(s) marked delivered.")

    @admin.action(description="Cancel selected orders")
    def mark_cancelled(self, request, queryset):
        count = 0
        for order in queryset.filter(order_status__in=[OrderStatus.PLACED, OrderStatus.CONFIRMED, OrderStatus.PREPARING]):
            order.set_status(OrderStatus.CANCELLED, note="Cancelled by admin", actor=request.user)
            count += 1
        self.message_user(request, f"{count} order(s) cancelled.")


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "food_name", "quantity", "price", "total")
    search_fields = ("order__order_number", "food_name")
    list_filter = ("is_veg",)


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("order", "status", "note", "created_by", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("order__order_number", "note")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "title", "kind", "is_read", "created_at")
    list_filter = ("kind", "is_read", "created_at")
    search_fields = ("recipient__email", "title", "message")
    autocomplete_fields = ("recipient", "order")
    list_per_page = 50
