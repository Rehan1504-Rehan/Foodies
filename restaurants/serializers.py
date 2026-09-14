"""DRF serializers for restaurants."""

from rest_framework import serializers

from restaurants.models import Restaurant


class RestaurantListSerializer(serializers.ModelSerializer):
    cuisines = serializers.ListField(read_only=True)
    url = serializers.CharField(source="get_absolute_url", read_only=True)

    class Meta:
        model = Restaurant
        fields = [
            "id", "name", "slug", "url", "logo", "cover_image", "cuisine_type", "cuisines",
            "rating", "rating_count", "delivery_time", "delivery_fee", "minimum_order",
            "area", "city", "is_open", "is_approved",
        ]


class RestaurantDetailSerializer(RestaurantListSerializer):
    owner_email = serializers.CharField(source="owner.email", read_only=True)
    menu_url = serializers.SerializerMethodField()

    class Meta(RestaurantListSerializer.Meta):
        fields = RestaurantListSerializer.Meta.fields + [
            "description", "phone", "email", "address", "state", "pincode",
            "owner_email", "menu_url", "created_at",
        ]

    def get_menu_url(self, obj):
        return f"/api/restaurants/{obj.slug}/menu/"
