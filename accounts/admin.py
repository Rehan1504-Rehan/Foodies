from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from .models import Address, User


class AddressInline(admin.TabularInline):
    model = Address
    extra = 0
    fields = ("full_name", "phone", "area", "city", "pincode", "address_type", "is_default")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "full_name", "role", "phone", "is_active", "is_staff", "date_joined")
    list_filter = ("role", "is_active", "is_staff", "is_superuser", "date_joined")
    search_fields = ("email", "first_name", "last_name", "phone")
    ordering = ("-date_joined",)
    list_per_page = 25
    inlines = [AddressInline]
    readonly_fields = ("date_joined", "last_login", "updated_at", "avatar_preview")
    actions = ["block_users", "unblock_users"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "phone", "profile_image", "avatar_preview")}),
        ("Role & status", {"fields": ("role", "is_active", "blocked_reason", "email_verified")}),
        ("Permissions", {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "first_name", "last_name", "phone", "role", "password1", "password2"),
            },
        ),
    )

    @admin.display(description="Photo")
    def avatar_preview(self, obj):
        if obj.profile_image:
            return format_html('<img src="{}" style="height:48px;border-radius:50%" />', obj.profile_image.url)
        return "—"

    @admin.action(description="Block selected accounts")
    def block_users(self, request, queryset):
        updated = queryset.exclude(pk=request.user.pk).update(is_active=False)
        self.message_user(request, f"{updated} account(s) blocked.")

    @admin.action(description="Unblock selected accounts")
    def unblock_users(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} account(s) activated.")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "area", "city", "pincode", "address_type", "is_default")
    list_filter = ("address_type", "city", "is_default")
    search_fields = ("full_name", "phone", "area", "city", "pincode", "user__email")
    autocomplete_fields = ("user",)
    list_per_page = 25
