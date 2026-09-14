from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.FoodieLoginView.as_view(), name="login"),
    path("logout/", views.FoodieLogoutView.as_view(), name="logout"),
    path("register/", views.register, {"role": "customer"}, name="register"),
    path("register/customer/", views.register, {"role": "customer"}, name="register_customer"),
    path("register/restaurant/", views.register, {"role": "restaurant"}, name="register_restaurant"),
    path("register/delivery/", views.register, {"role": "delivery"}, name="register_delivery"),
    path("profile/", views.profile, name="profile"),
    path("addresses/", views.address_list, name="addresses"),
    path("addresses/new/", views.address_create, name="address_create"),
    path("addresses/<int:pk>/edit/", views.address_edit, name="address_edit"),
    path("addresses/<int:pk>/delete/", views.address_delete, name="address_delete"),
    path("addresses/<int:pk>/default/", views.address_set_default, name="address_default"),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/<int:pk>/read/", views.notification_read, name="notification_read"),
]
