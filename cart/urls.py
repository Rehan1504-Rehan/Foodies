from django.urls import path

from cart import views

app_name = "cart"

urlpatterns = [
    path("", views.cart_detail, name="detail"),
    path("summary/", views.cart_summary_api, name="summary"),
    path("add/<int:pk>/", views.add_to_cart, name="add"),
    path("update/<int:pk>/", views.update_cart_item, name="update"),
    path("remove/<int:pk>/", views.remove_from_cart, name="remove"),
    path("clear/", views.clear_cart, name="clear"),
    path("coupon/apply/", views.apply_coupon, name="apply_coupon"),
    path("coupon/remove/", views.remove_coupon, name="remove_coupon"),
]
