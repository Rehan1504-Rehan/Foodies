from django.urls import path

from delivery import views

app_name = "delivery"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("available/", views.available_orders, name="available"),
    path("earnings/", views.earnings, name="earnings"),
    path("history/", views.history, name="history"),
    path("profile/", views.profile_view, name="profile"),
    path("availability/", views.toggle_availability, name="toggle_availability"),
    path("orders/<str:order_number>/", views.order_detail, name="order_detail"),
    path("orders/<str:order_number>/claim/", views.claim_order, name="claim"),
    path("orders/<str:order_number>/status/<str:status>/", views.update_status, name="update_status"),
]
