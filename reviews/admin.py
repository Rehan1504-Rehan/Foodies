from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("restaurant", "customer", "rating", "short_comment", "is_hidden", "created_at")
    list_filter = ("rating", "is_hidden", "created_at", "restaurant")
    search_fields = ("restaurant__name", "customer__email", "comment")
    autocomplete_fields = ("customer", "restaurant", "order")
    list_editable = ("is_hidden",)
    date_hierarchy = "created_at"
    actions = ["hide_reviews", "unhide_reviews"]

    @admin.display(description="Comment")
    def short_comment(self, obj):
        return (obj.comment[:60] + "…") if len(obj.comment) > 60 else (obj.comment or "—")

    @admin.action(description="Hide selected reviews")
    def hide_reviews(self, request, queryset):
        queryset.update(is_hidden=True)
        for restaurant in {r.restaurant for r in queryset}:
            restaurant.recalculate_rating()
        self.message_user(request, "Selected reviews hidden.")

    @admin.action(description="Unhide selected reviews")
    def unhide_reviews(self, request, queryset):
        queryset.update(is_hidden=False)
        for restaurant in {r.restaurant for r in queryset}:
            restaurant.recalculate_rating()
        self.message_user(request, "Selected reviews restored.")
