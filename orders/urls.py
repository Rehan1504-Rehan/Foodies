from django.urls import path

from orders import views

app_name = "orders"

urlpatterns = [
    path("", views.order_list, name="list"),
    path("<str:order_number>/", views.order_detail, name="detail"),
    path("<str:order_number>/track/", views.order_track, name="track"),
    path("<str:order_number>/cancel/", views.order_cancel, name="cancel"),
    path("<str:order_number>/reorder/", views.reorder, name="reorder"),
    path("<str:order_number>/invoice/", views.order_invoice, name="invoice"),
]
