"""FOODIES REST API routes (/api/...).

Uses DRF routers so every endpoint exposes list / retrieve / create / update /
delete where it makes sense, with role-based permissions and throttling.
"""

from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from accounts import api as accounts_api
from cart import api as cart_api
from delivery import api as delivery_api
from menu import api as menu_api
from offers import api as offers_api
from orders import api as orders_api
from payments import api as payments_api
from restaurants import api as restaurants_api
from reviews import api as reviews_api

router = DefaultRouter(trailing_slash=True)
router.register("restaurants", restaurants_api.RestaurantViewSet, basename="api-restaurants")
router.register("categories", menu_api.CategoryViewSet, basename="api-categories")
router.register("food", menu_api.FoodItemViewSet, basename="api-food")
router.register("orders", orders_api.OrderViewSet, basename="api-orders")
router.register("reviews", reviews_api.ReviewViewSet, basename="api-reviews")
router.register("delivery/assignments", delivery_api.DeliveryAssignmentViewSet, basename="api-delivery-assignments")
router.register("delivery/profile", delivery_api.DeliveryProfileViewSet, basename="api-delivery-profile")
router.register("addresses", accounts_api.AddressViewSet, basename="api-addresses")
router.register("offers", offers_api.CouponViewSet, basename="api-offers")
router.register("notifications", orders_api.NotificationViewSet, basename="api-notifications")

app_name = "api"

urlpatterns = [
    # Auth
    path("auth/register/", accounts_api.register, name="register"),
    path("auth/login/", accounts_api.login_view, name="login"),
    path("auth/logout/", accounts_api.logout_view, name="logout"),
    path("auth/token/", obtain_auth_token, name="token"),
    path("auth/me/", accounts_api.me, name="me"),

    # Cart
    path("cart/", cart_api.cart_detail, name="cart"),
    path("cart/summary/", cart_api.cart_detail, name="cart-summary"),
    path("cart/add/", cart_api.add_item, name="cart-add"),
    path("cart/update/", cart_api.update_item, name="cart-update"),
    path("cart/remove/", cart_api.remove_item, name="cart-remove"),
    path("cart/clear/", cart_api.clear, name="cart-clear"),
    path("cart/coupon/", cart_api.apply_coupon, name="cart-coupon"),
    path("cart/coupon/remove/", cart_api.remove_coupon, name="cart-coupon-remove"),

    # Payments
    path("payments/", payments_api.payment_list, name="payments"),
    path("payments/config/", payments_api.payment_config, name="payment-config"),
    path("payments/confirm/", payments_api.confirm_payment, name="payment-confirm"),
    path("payments/order/<str:order_number>/create/", payments_api.create_order_payment, name="payment-create"),
    path("payments/<str:payment_id>/", payments_api.payment_detail, name="payment-detail"),

    # Notifications helper
    path("notifications/unread-count/", orders_api.unread_count, name="notifications-unread"),

    # Browsable API + router endpoints
    path("", include(router.urls)),
    path("auth/", include("rest_framework.urls")),
]
