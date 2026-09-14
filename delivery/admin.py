from django.contrib import admin

from .models import DeliveryAssignment, DeliveryBoyProfile, DeliveryEarning


@admin.register(DeliveryBoyProfile)
class DeliveryBoyProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user", "vehicle_type", "vehicle_number", "current_area",
        "availability_status", "is_approved", "completed_count", "total_earnings",
    )
    list_filter = ("availability_status", "is_approved", "vehicle_type")
    search_fields = ("user__email", "user__first_name", "user__phone", "vehicle_number", "license_number")
    autocomplete_fields = ("user",)
    list_editable = ("is_approved", "availability_status")
    actions = ["approve_partners", "set_online", "set_offline"]

    @admin.action(description="Approve selected delivery partners")
    def approve_partners(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f"{updated} partner(s) approved.")

    @admin.action(description="Mark selected partners ONLINE")
    def set_online(self, request, queryset):
        queryset.update(availability_status=DeliveryBoyProfile.Availability.ONLINE)
        self.message_user(request, "Partners set to online.")

    @admin.action(description="Mark selected partners OFFLINE")
    def set_offline(self, request, queryset):
        queryset.update(availability_status=DeliveryBoyProfile.Availability.OFFLINE)
        self.message_user(request, "Partners set to offline.")


@admin.register(DeliveryAssignment)
class DeliveryAssignmentAdmin(admin.ModelAdmin):
    list_display = ("order", "delivery_boy", "status", "distance_km", "earning_amount", "assigned_at", "delivered_at")
    list_filter = ("status", "assigned_at")
    search_fields = ("order__order_number", "delivery_boy__email", "delivery_boy__first_name")
    autocomplete_fields = ("order", "delivery_boy", "assigned_by")
    readonly_fields = ("assigned_at", "accepted_at", "picked_up_at", "out_for_delivery_at", "delivered_at")


@admin.register(DeliveryEarning)
class DeliveryEarningAdmin(admin.ModelAdmin):
    list_display = ("delivery_boy", "order", "amount", "status", "created_at", "settled_at")
    list_filter = ("status", "created_at")
    search_fields = ("delivery_boy__email", "order__order_number")
    autocomplete_fields = ("delivery_boy", "order", "assignment")
    actions = ["settle_earnings"]

    @admin.action(description="Mark selected earnings as settled")
    def settle_earnings(self, request, queryset):
        from django.utils import timezone

        updated = queryset.update(status=DeliveryEarning.Status.SETTLED, settled_at=timezone.now())
        self.message_user(request, f"{updated} earning(s) settled.")
