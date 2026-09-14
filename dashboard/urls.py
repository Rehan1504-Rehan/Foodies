"""Dashboard URLs for the FOODIES admin and restaurant owner interfaces."""

from django.urls import path

from dashboard import admin_views as a
from dashboard import customer_views as c
from dashboard import restaurant_views as r
from dashboard import views

app_name = "dashboard"

urlpatterns = [
    # Entry point (post-login landing + friendly aliases)
    path("dashboard/", views.dashboard_redirect, name="redirect"),
    path("dashboard/customer/", c.customer_home, name="customer_home_alias"),

    # ---------------------------------------------------------------- admin
    path("admin-dashboard/", a.admin_home, name="admin_home"),
    path("admin-dashboard/customers/", a.customers, name="admin_customers"),
    path("admin-dashboard/restaurant-owners/", a.restaurant_owners, name="admin_restaurant_owners"),
    path("admin-dashboard/users/<int:pk>/toggle/", a.toggle_user_active, name="admin_toggle_user"),
    path("admin-dashboard/restaurants/", a.restaurants, name="admin_restaurants"),
    path("admin-dashboard/restaurants/<int:pk>/", a.restaurant_detail, name="admin_restaurant_detail"),
    path("admin-dashboard/restaurants/<int:pk>/toggle-open/", a.toggle_restaurant_open, name="admin_toggle_restaurant"),
    path("admin-dashboard/approvals/", a.approvals, name="admin_approvals"),
    path("admin-dashboard/approvals/<int:pk>/approve/", a.approve_restaurant, name="admin_approve_restaurant"),
    path("admin-dashboard/approvals/<int:pk>/reject/", a.reject_restaurant, name="admin_reject_restaurant"),
    path("admin-dashboard/delivery-boys/", a.delivery_boys, name="admin_delivery_boys"),
    path("admin-dashboard/delivery-boys/create/", a.delivery_boy_create, name="admin_delivery_boy_create"),
    path("admin-dashboard/delivery-boys/<int:pk>/approve/", a.toggle_delivery_approval, name="admin_toggle_delivery"),
    path("admin-dashboard/delivery/", a.delivery_assignments, name="admin_delivery_assignments"),
    path("admin-dashboard/delivery/<str:order_number>/assign/", a.assign_partner, name="admin_assign_partner"),
    path("admin-dashboard/categories/", a.categories, name="admin_categories"),
    path("admin-dashboard/categories/new/", a.category_form, name="admin_category_create"),
    path("admin-dashboard/categories/<int:pk>/edit/", a.category_form, name="admin_category_edit"),
    path("admin-dashboard/categories/<int:pk>/delete/", a.category_delete, name="admin_category_delete"),
    path("admin-dashboard/food/", a.food_items, name="admin_food_items"),
    path("admin-dashboard/food/<int:pk>/toggle/", a.toggle_food_availability, name="admin_toggle_food"),
    path("admin-dashboard/food/<int:pk>/delete/", a.delete_food_item, name="admin_delete_food"),
    path("admin-dashboard/orders/", a.orders, name="admin_orders"),
    path("admin-dashboard/orders/<str:order_number>/", a.order_detail, name="admin_order_detail"),
    path("admin-dashboard/orders/<str:order_number>/status/", a.update_order_status, name="admin_order_status"),
    path("admin-dashboard/payments/", a.payments, name="admin_payments"),
    path("admin-dashboard/coupons/", a.coupons, name="admin_coupons"),
    path("admin-dashboard/coupons/new/", a.coupon_form, name="admin_coupon_create"),
    path("admin-dashboard/coupons/<int:pk>/edit/", a.coupon_form, name="admin_coupon_edit"),
    path("admin-dashboard/coupons/<int:pk>/toggle/", a.toggle_coupon, name="admin_toggle_coupon"),
    path("admin-dashboard/coupons/<int:pk>/delete/", a.delete_coupon, name="admin_delete_coupon"),
    path("admin-dashboard/reviews/", a.reviews, name="admin_reviews"),
    path("admin-dashboard/reviews/<int:pk>/toggle/", a.toggle_review_visibility, name="admin_toggle_review"),
    path("admin-dashboard/reviews/<int:pk>/delete/", a.delete_review, name="admin_delete_review"),
    path("admin-dashboard/reports/", a.reports, name="admin_reports"),
    path("admin-dashboard/settings/", a.settings_view, name="admin_settings"),

    # ----------------------------------------------------------- restaurant
    path("restaurant-dashboard/", r.restaurant_home, name="restaurant_home"),
    path("restaurant-dashboard/restaurant/", r.restaurant_profile, name="restaurant_profile"),
    path("restaurant-dashboard/restaurant/create/", r.restaurant_create, name="restaurant_restaurant_create"),
    path("restaurant-dashboard/restaurant/toggle-open/", r.toggle_restaurant_open, name="restaurant_toggle_open"),
    path("restaurant-dashboard/menu/", r.menu_items, name="restaurant_menu"),
    path("restaurant-dashboard/menu/new/", r.food_item_form, name="restaurant_food_create"),
    path("restaurant-dashboard/menu/<int:pk>/edit/", r.food_item_form, name="restaurant_food_edit"),
    path("restaurant-dashboard/menu/<int:pk>/toggle/", r.toggle_food_availability, name="restaurant_toggle_food"),
    path("restaurant-dashboard/menu/<int:pk>/delete/", r.delete_food_item, name="restaurant_delete_food"),
    path("restaurant-dashboard/categories/", r.categories, name="restaurant_categories"),
    path("restaurant-dashboard/orders/", r.orders, name="restaurant_orders"),
    path("restaurant-dashboard/orders/<str:order_number>/", r.order_detail, name="restaurant_order_detail"),
    path("restaurant-dashboard/orders/<str:order_number>/<str:action>/", r.order_action, name="restaurant_order_action"),
    path("restaurant-dashboard/reviews/", r.reviews, name="restaurant_reviews"),
    path("restaurant-dashboard/reviews/<int:pk>/reply/", r.reply_review, name="restaurant_reply_review"),
    path("restaurant-dashboard/offers/", r.coupons, name="restaurant_offers"),
    path("restaurant-dashboard/offers/<int:pk>/toggle/", r.toggle_coupon, name="restaurant_toggle_coupon"),
    path("restaurant-dashboard/sales/", r.sales, name="restaurant_sales"),
    path("restaurant-dashboard/profile/", r.profile_settings, name="restaurant_profile_settings"),

    # ------------------------------------------------------------ customer
    path("customer/", c.customer_home, name="customer_home"),
]
