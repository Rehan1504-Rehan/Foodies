"""DRF serializers for categories and food items."""

from rest_framework import serializers

from menu.models import Category, FoodItem


class CategorySerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(read_only=True)
    url = serializers.CharField(source="get_absolute_url", read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "image", "icon", "item_count", "url", "is_active"]


class FoodItemSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source="restaurant.name", read_only=True)
    restaurant_slug = serializers.CharField(source="restaurant.slug", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    final_price = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    discount_percent = serializers.IntegerField(read_only=True)
    has_discount = serializers.BooleanField(read_only=True)
    food_type = serializers.CharField(read_only=True)

    class Meta:
        model = FoodItem
        fields = [
            "id", "name", "slug", "description", "price", "discount_price", "final_price",
            "discount_percent", "has_discount", "image", "is_veg", "food_type", "is_available",
            "is_recommended", "preparation_time", "order_count", "rating",
            "restaurant", "restaurant_name", "restaurant_slug", "category", "category_name",
            "created_at", "updated_at",
        ]
        read_only_fields = ["order_count", "rating", "slug"]

    def validate(self, attrs):
        price = attrs.get("price", getattr(self.instance, "price", None))
        discount_price = attrs.get("discount_price", getattr(self.instance, "discount_price", None))
        if discount_price is not None and price is not None and discount_price >= price:
            raise serializers.ValidationError({"discount_price": "Discount price must be lower than the base price."})
        return attrs
