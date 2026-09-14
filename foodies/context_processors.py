"""Template context shared by every FOODIES page."""

from django.conf import settings


def site_context(request):
    cart_count = 0
    unread_notifications = 0
    current_role = None
    food_quantities = {}
    pending_approval_count = 0
    new_orders_count = 0

    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        current_role = user.role

        if user.is_customer:
            from cart.models import Cart

            cart = Cart.objects.filter(user=user).prefetch_related("cart_items").first()
            if cart:
                cart_count = cart.total_items
                food_quantities = {item.food_item_id: item.quantity for item in cart.cart_items.all()}

        from orders.models import Notification

        unread_notifications = Notification.objects.filter(recipient=user, is_read=False).count()

        # Sidebar badges for the dashboard shells.
        if user.is_superuser or user.role == "ADMIN":
            from restaurants.models import Restaurant

            pending_approval_count = Restaurant.objects.filter(is_approved=False, is_active=True).count()
        elif user.role == "RESTAURANT_OWNER":
            from restaurants.models import Restaurant

            restaurant = Restaurant.objects.filter(owner=user).first()
            if restaurant:
                new_orders_count = restaurant.orders.filter(order_status="PLACED").count()

    return {
        "SITE_NAME": settings.SITE_NAME,
        "SITE_TAGLINE": settings.SITE_TAGLINE,
        "CURRENCY": settings.DEFAULT_CURRENCY,
        "cart_count": cart_count,
        "food_quantities": food_quantities,
        "unread_notifications": unread_notifications,
        "current_role": current_role,
        "pending_approval_count": pending_approval_count,
        "new_orders_count": new_orders_count,
    }
