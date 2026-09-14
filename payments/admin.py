from django.contrib import admin
from django.utils.html import format_html

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("payment_id", "order", "amount", "payment_method", "status_badge", "created_at")
    list_filter = ("payment_method", "status", "created_at")
    search_fields = ("payment_id", "gateway_order_id", "order__order_number", "order__customer__email")
    autocomplete_fields = ("order",)
    readonly_fields = ("created_at", "updated_at", "gateway_response", "gateway_signature")
    date_hierarchy = "created_at"
    list_per_page = 25

    @admin.display(description="Status")
    def status_badge(self, obj):
        colours = {"SUCCESS": "#16a34a", "PENDING": "#f59e0b", "FAILED": "#dc2626", "REFUNDED": "#6366f1"}
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:999px;font-size:11px">{}</span>',
            colours.get(obj.status, "#64748b"),
            obj.status,
        )
